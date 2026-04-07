"""SEC filings ingestion service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Any, Callable
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models import SourceItem, WatchlistSymbol
from backend.app.services.news.news_ingestion_service import compute_content_hash, store_source_items
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run

logger = logging.getLogger(__name__)

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def ingest_sec_filings(
    db: Session,
    symbols: list[str],
    start_time: datetime,
    end_time: datetime,
    *,
    settings: Settings | None = None,
    fetch_json: Callable[[str, dict[str, str]], Any] | None = None,
) -> dict[str, Any]:
    """Fetch, normalize, and store recent SEC filings for the given symbols."""

    resolved_settings = settings or get_settings()
    run = start_pipeline_run(
        db,
        run_type="sec_ingestion",
        trigger_type="manual",
        provider_used="sec",
        metrics_json={"symbol_count": len(symbols)},
    )
    if not resolved_settings.sec_user_agent:
        error = ValueError("SEC_USER_AGENT is required for SEC ingestion.")
        fail_pipeline_run(db, run, error=error, metrics_json={"symbol_count": len(symbols)}, provider_used="sec")
        raise error

    normalized_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not normalized_symbols:
        logger.info("No symbols provided for SEC ingestion.")
        stats = {
            "provider_used": "sec",
            "fetched_count": 0,
            "inserted_count": 0,
            "skipped_duplicates": 0,
            "mapped_symbol_count": 0,
        }
        complete_pipeline_run(db, run, metrics_json=stats, provider_used="sec")
        return stats

    try:
        fetch_json_fn = fetch_json or _fetch_json
        ticker_mapping = load_company_ticker_mapping(resolved_settings, fetch_json=fetch_json_fn)
        filings: list[dict[str, Any]] = []
        mapped_symbols = 0

        for symbol in normalized_symbols:
            company_info = ticker_mapping.get(symbol)
            if company_info is None:
                logger.warning("No SEC company mapping found for symbol=%s", symbol)
                continue

            mapped_symbols += 1
            submissions_url = SEC_SUBMISSIONS_URL.format(cik=company_info["cik_padded"])
            submissions = fetch_json_fn(submissions_url, _sec_headers(resolved_settings))
            filings.extend(
                _extract_recent_filings(
                    submissions=submissions,
                    symbol=symbol,
                    company_info=company_info,
                    start_time=start_time.astimezone(UTC),
                    end_time=end_time.astimezone(UTC),
                )
            )

        stats = store_source_items(db, filings, source_type="filing")
        logger.info(
            "SEC ingestion complete symbols=%s mapped_symbols=%s fetched=%s inserted=%s duplicates=%s",
            normalized_symbols,
            mapped_symbols,
            stats["fetched_count"],
            stats["inserted_count"],
            stats["skipped_duplicates"],
        )
        final_stats = {
            "provider_used": "sec",
            "mapped_symbol_count": mapped_symbols,
            **stats,
        }
        complete_pipeline_run(db, run, metrics_json=final_stats, provider_used="sec")
        return final_stats
    except Exception as exc:
        fail_pipeline_run(
            db,
            run,
            error=exc,
            metrics_json={"symbol_count": len(normalized_symbols)},
            provider_used="sec",
        )
        logger.exception("SEC ingestion failed for symbols=%s", normalized_symbols)
        raise


def get_watchlist_symbols(db: Session, watchlist_id: int | None = None) -> list[str]:
    """Load watchlist symbols for SEC ingestion."""

    statement = select(WatchlistSymbol.symbol).order_by(WatchlistSymbol.symbol.asc())
    if watchlist_id is not None:
        statement = statement.where(WatchlistSymbol.watchlist_id == watchlist_id)
    return list(db.execute(statement).scalars().all())


def load_company_ticker_mapping(
    settings: Settings | None = None,
    *,
    fetch_json: Callable[[str, dict[str, str]], Any] | None = None,
) -> dict[str, dict[str, str]]:
    """Load the SEC ticker-to-company mapping."""

    resolved_settings = settings or get_settings()
    if not resolved_settings.sec_user_agent:
        raise ValueError("SEC_USER_AGENT is required for SEC ingestion.")

    fetch_json_fn = fetch_json or _fetch_json
    if fetch_json is None:
        return _cached_company_ticker_mapping(resolved_settings.sec_user_agent)

    payload = fetch_json_fn(SEC_TICKERS_URL, _sec_headers(resolved_settings))
    return _normalize_company_ticker_mapping(payload)


@lru_cache(maxsize=4)
def _cached_company_ticker_mapping(user_agent: str) -> dict[str, dict[str, str]]:
    payload = _fetch_json(SEC_TICKERS_URL, {"User-Agent": user_agent, "Accept": "application/json"})
    return _normalize_company_ticker_mapping(payload)


def _normalize_company_ticker_mapping(payload: Any) -> dict[str, dict[str, str]]:
    if not isinstance(payload, dict):
        raise ValueError("SEC company ticker mapping returned an unexpected payload shape.")

    mapping: dict[str, dict[str, str]] = {}
    for record in payload.values():
        if not isinstance(record, dict):
            continue
        ticker = str(record.get("ticker") or "").strip().upper()
        cik_value = record.get("cik_str")
        company_name = str(record.get("title") or "").strip()
        if not ticker or cik_value is None or not company_name:
            continue
        cik = str(int(cik_value))
        mapping[ticker] = {
            "ticker": ticker,
            "company_name": company_name,
            "cik": cik,
            "cik_padded": cik.zfill(10),
        }
    return mapping


def _extract_recent_filings(
    *,
    submissions: Any,
    symbol: str,
    company_info: dict[str, str],
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    recent = submissions.get("filings", {}).get("recent", {}) if isinstance(submissions, dict) else {}
    accession_numbers = list(recent.get("accessionNumber") or [])
    filing_dates = list(recent.get("filingDate") or [])
    form_types = list(recent.get("form") or [])
    primary_documents = list(recent.get("primaryDocument") or [])
    primary_descriptions = list(recent.get("primaryDocDescription") or [])

    max_length = min(
        len(accession_numbers),
        len(filing_dates),
        len(form_types),
        len(primary_documents),
    )
    items: list[dict[str, Any]] = []

    for index in range(max_length):
        filing_date = _parse_filing_date(filing_dates[index])
        if filing_date is None or filing_date < start_time or filing_date > end_time:
            continue

        accession_number = str(accession_numbers[index]).strip()
        form_type = str(form_types[index]).strip()
        primary_document = str(primary_documents[index]).strip()
        primary_description = str(primary_descriptions[index]).strip() if index < len(primary_descriptions) else ""
        title = f"{symbol} filed {form_type}"
        if primary_description:
            title = f"{title} - {primary_description}"
        body_text = (
            f"{company_info['company_name']} filed Form {form_type} with the SEC on {filing_date.date().isoformat()}."
        )
        if primary_description:
            body_text = f"{body_text} {primary_description}"

        archive_url = _build_filing_url(company_info["cik"], accession_number, primary_document)
        metadata_json = {
            "provider": "sec",
            "ticker": symbol,
            "company_name": company_info["company_name"],
            "cik": company_info["cik"],
            "accession_number": accession_number,
            "form_type": form_type,
            "filing_date": filing_date.date().isoformat(),
            "primary_document": primary_document,
            "primary_document_description": primary_description or None,
        }
        items.append(
            {
                "external_id": accession_number,
                "title": title,
                "body_text": body_text,
                "url": archive_url,
                "source_name": "sec",
                "published_at": filing_date,
                "metadata_json": metadata_json,
                "content_hash": compute_content_hash(title, archive_url),
            }
        )

    return items


def _build_filing_url(cik: str, accession_number: str, primary_document: str) -> str:
    accession_without_dashes = accession_number.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession_without_dashes}/{primary_document}"
    )


def _parse_filing_date(value: Any) -> datetime | None:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _sec_headers(settings: Settings) -> dict[str, str]:
    return {
        "User-Agent": str(settings.sec_user_agent),
        "Accept": "application/json",
    }


def _fetch_json(url: str, headers: dict[str, str]) -> Any:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))
