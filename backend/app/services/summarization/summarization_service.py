"""Baseline cluster summarization helpers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.app.models import SourceItem


def summarize_cluster(cluster_articles: list[SourceItem]) -> str:
    """Build a deterministic baseline summary for clustered articles."""

    if not cluster_articles:
        return ""

    sorted_articles = sorted(
        cluster_articles,
        key=lambda item: (item.is_representative is False, item.published_at, item.id),
    )
    top_titles = [article.title.strip() for article in sorted_articles[:3] if article.title.strip()]
    title_summary = "; ".join(dict.fromkeys(top_titles))

    key_sentences: list[str] = []
    for article in sorted_articles[:2]:
        sentence = _extract_key_sentence(article.body_text)
        if sentence and sentence not in key_sentences:
            key_sentences.append(sentence)

    parts = [part for part in [title_summary, " ".join(key_sentences)] if part]
    return " ".join(parts).strip()


class BaselineClusterSummaryResult(BaseModel):
    """Structured baseline summary result."""

    headline: str
    summary_bullets: list[str]
    why_it_matters: str
    confidence: Literal["high", "medium", "low"]
    unknowns: list[str]
    cited_source_indices: list[int]
    rendered_summary_text: str
    model_name: str
    prompt_version: str


def build_baseline_cluster_summary_result(cluster_articles: list[SourceItem]) -> BaselineClusterSummaryResult:
    """Build a deterministic structured baseline summary."""

    if not cluster_articles:
        raise ValueError("Cluster summarization requires at least one article.")

    sorted_articles = sorted(
        cluster_articles,
        key=lambda item: (item.is_representative is False, item.published_at, item.id),
    )
    headline = sorted_articles[0].title.strip()
    bullets = [article.title.strip() for article in sorted_articles[:3] if article.title.strip()]
    why_it_matters = _extract_key_sentence(sorted_articles[0].body_text) or headline
    cited_source_indices = list(range(min(len(sorted_articles), 2)))
    confidence = "high" if len(sorted_articles) >= 2 else "medium"
    unknowns = ["Coverage is limited to the provided source set."] if len(sorted_articles) == 1 else []
    rendered_summary_text = summarize_cluster(sorted_articles)
    return BaselineClusterSummaryResult(
        headline=headline,
        summary_bullets=bullets,
        why_it_matters=why_it_matters,
        confidence=confidence,
        unknowns=unknowns,
        cited_source_indices=cited_source_indices,
        rendered_summary_text=rendered_summary_text,
        model_name="baseline",
        prompt_version="cluster_summary_v1",
    )


def _extract_key_sentence(body_text: str) -> str:
    """Return a short leading sentence from article text."""

    cleaned = " ".join(body_text.split()).strip()
    if not cleaned:
        return ""

    sentence = cleaned.split(".")[0].strip()
    if not sentence:
        return ""
    if not sentence.endswith("."):
        sentence = f"{sentence}."
    return sentence
