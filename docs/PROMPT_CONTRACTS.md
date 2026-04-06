# Prompt Contracts

## Cluster Summary Contract

### Input

* cluster_id
* source packet ordered by `source_index`
* each source item includes:
  * `source_index`
  * `source_name`
  * `title`
  * `published_at`
  * `url`
  * trimmed `body_text_excerpt`

---

### Output Schema (JSON ONLY)

{
  "headline": "string",
  "summary_bullets": ["string"],
  "why_it_matters": "string",
  "confidence": "high | medium | low",
  "unknowns": ["string"],
  "cited_source_indices": [0]
}

---

## Grounding Rules

* Use only facts present in the provided source packet
* Do NOT speculate beyond the sources
* Do NOT provide investment advice
* Do NOT claim price impact unless the sources explicitly support it
* Prefer consensus facts repeated across multiple articles
* Preserve contradictions or thin sourcing in `unknowns`
* `cited_source_indices` must reference valid `source_index` values from the input
* Must return valid JSON that matches the schema exactly

---

## Digest Assembly Contract

### Input

* ranked cluster summaries
* watchlist

### Output

Structured digest sections:

* Must Know
* Watch at Open
* SEC Filings
* Likely Noise

---

## Validation Requirements

* JSON must parse successfully
* Required fields must be present
* `cited_source_indices` must be within the source packet bounds
* Reject malformed outputs
* Retry or fallback on failure
