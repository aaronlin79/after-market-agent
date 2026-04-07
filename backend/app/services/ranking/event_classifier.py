"""Keyword-based event classification."""

from __future__ import annotations


EVENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("earnings", ("earnings", "quarterly results", "revenue", "eps")),
    ("guidance", ("guidance", "outlook", "forecast", "raises outlook", "cuts outlook")),
    ("sec_filing", ("8-k", "10-q", "10-k", "sec filing", "filing")),
    ("m_and_a", ("acquire", "acquisition", "merger", "buyout", "takeover")),
    ("management_change", ("ceo", "cfo", "chairman", "appoints", "resigns", "steps down")),
    ("product_launch", ("launch", "unveils", "introduces", "release", "debut")),
    ("lawsuit_or_regulation", ("lawsuit", "probe", "regulator", "investigation", "fined", "settlement")),
    ("analyst_action", ("upgrades", "downgrade", "price target", "analyst", "initiates coverage")),
    ("rumor", ("reportedly", "rumor", "speculation", "said to", "people familiar")),
]


def classify_event_type(text: str) -> str | None:
    """Classify a cluster event type using simple keyword heuristics."""

    normalized = text.lower()
    for label, keywords in EVENT_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return label
    return "other" if normalized.strip() else None
