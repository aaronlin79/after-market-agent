"""OpenAI-backed cluster summarization with structured outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.core.config import Settings, get_settings
from backend.app.models import SourceItem
from backend.app.services.openai.openai_client import OpenAIResponsesClient

PROMPT_VERSION = "cluster_summary_v2"
MAX_SOURCES = 6
MAX_BODY_CHARS = 700


class ClusterSummaryStructuredOutput(BaseModel):
    """Strict structured output for cluster summarization."""

    headline: str = Field(..., min_length=1)
    summary_bullets: list[str] = Field(..., min_length=1)
    why_it_matters: str = Field(..., min_length=1)
    confidence: Literal["high", "medium", "low"]
    unknowns: list[str] = Field(default_factory=list)
    cited_source_indices: list[int] = Field(..., min_length=1)

    @field_validator("summary_bullets")
    @classmethod
    def validate_bullets(cls, value: list[str]) -> list[str]:
        bullets = [bullet.strip() for bullet in value if bullet.strip()]
        if not bullets:
            raise ValueError("summary_bullets must contain at least one non-empty bullet.")
        return bullets

    @field_validator("headline", "why_it_matters")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Required text field cannot be blank.")
        return normalized


class ClusterSummaryResult(BaseModel):
    """Validated cluster summary result used by persistence."""

    headline: str
    summary_bullets: list[str]
    why_it_matters: str
    confidence: Literal["high", "medium", "low"]
    unknowns: list[str]
    cited_source_indices: list[int]
    rendered_summary_text: str
    model_name: str
    prompt_version: str


def summarize_cluster_with_openai(
    cluster_articles: list[SourceItem],
    *,
    settings: Settings | None = None,
    client: OpenAIResponsesClient | None = None,
) -> ClusterSummaryResult:
    """Summarize a cluster with OpenAI structured outputs."""

    if not cluster_articles:
        raise ValueError("Cluster summarization requires at least one article.")

    resolved_settings = settings or get_settings()
    source_packet = build_source_packet(cluster_articles)
    openai_client = client or OpenAIResponsesClient(settings=resolved_settings)
    parsed, model_name = openai_client.parse_structured_output(
        instructions=_build_system_instructions(),
        input_text=_build_user_prompt(source_packet),
        response_model=ClusterSummaryStructuredOutput,
    )
    _validate_citations(parsed.cited_source_indices, len(source_packet))

    return ClusterSummaryResult(
        headline=parsed.headline,
        summary_bullets=parsed.summary_bullets,
        why_it_matters=parsed.why_it_matters,
        confidence=parsed.confidence,
        unknowns=parsed.unknowns,
        cited_source_indices=parsed.cited_source_indices,
        rendered_summary_text=render_summary_text(parsed),
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
    )


def build_source_packet(cluster_articles: list[SourceItem]) -> list[dict[str, Any]]:
    """Build a compact grounded source packet for the model."""

    sorted_articles = sorted(
        cluster_articles,
        key=lambda item: (item.is_representative is False, item.published_at, item.id),
    )[:MAX_SOURCES]
    packet: list[dict[str, Any]] = []
    for index, article in enumerate(sorted_articles):
        packet.append(
            {
                "source_index": index,
                "source_name": article.source_name,
                "title": article.title.strip(),
                "published_at": _format_datetime(article.published_at),
                "url": article.url,
                "body_text_excerpt": _trim_text(article.body_text),
            }
        )
    return packet


def render_summary_text(result: ClusterSummaryStructuredOutput) -> str:
    """Render a human-readable summary from structured output."""

    bullets = " ".join(f"- {bullet}" for bullet in result.summary_bullets)
    unknowns = " ".join(f"- {item}" for item in result.unknowns) if result.unknowns else "- None noted."
    citations = ", ".join(str(index) for index in result.cited_source_indices)
    return (
        f"{result.headline}\n"
        f"{bullets}\n"
        f"Why it matters: {result.why_it_matters}\n"
        f"Confidence: {result.confidence}\n"
        f"Unknowns: {unknowns}\n"
        f"Cited source indices: {citations}"
    ).strip()


def _build_system_instructions() -> str:
    return (
        "You generate grounded after-market news cluster summaries. "
        "Only use facts from the provided sources. "
        "Do not speculate, do not provide investment advice, and do not infer price impact unless sources explicitly say so. "
        "When sources are thin or contradictory, lower confidence and include the uncertainty in unknowns. "
        "Cited source indices must exactly match the provided source_index values."
    )


def _build_user_prompt(source_packet: list[dict[str, Any]]) -> str:
    lines = [
        "Summarize this cluster into the required structured schema.",
        "Use only the source packet below.",
        "Return cited_source_indices using the source_index numbers exactly.",
        "",
        "Source packet:",
    ]
    for source in source_packet:
        lines.extend(
            [
                f"[{source['source_index']}] {source['source_name']} | {source['published_at']}",
                f"Title: {source['title']}",
                f"URL: {source['url']}",
                f"Excerpt: {source['body_text_excerpt']}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _validate_citations(cited_source_indices: list[int], source_count: int) -> None:
    if not cited_source_indices:
        raise ValueError("OpenAI summary must cite at least one source index.")
    invalid = [index for index in cited_source_indices if index < 0 or index >= source_count]
    if invalid:
        raise ValueError(f"OpenAI summary returned invalid cited_source_indices: {invalid}")


def _trim_text(text: str) -> str:
    cleaned = " ".join(text.split()).strip()
    return cleaned[:MAX_BODY_CHARS]


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()
