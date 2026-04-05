"""Baseline cluster summarization helpers."""

from __future__ import annotations

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
