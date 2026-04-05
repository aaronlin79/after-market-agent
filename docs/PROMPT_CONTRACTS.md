# Prompt Contracts

## Cluster Summary Contract

### Input

* cluster_id
* representative title
* source items:

  * title
  * body text
  * source name
  * URL
  * published_at
* linked tickers
* event type (optional)

---

### Output (JSON ONLY)

{
"headline": "string",
"summary_bullets": ["string"],
"why_it_matters": "string",
"confidence": "high | medium | low",
"evidence": [
{
"source": "string",
"url": "string"
}
],
"unknowns": ["string"]
}

---

## Rules

* Do NOT speculate beyond sources
* Do NOT provide investment advice
* Do NOT claim price impact without evidence
* Must reference at least one source
* Must return valid JSON only
* Preserve uncertainty where applicable

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
* Reject malformed outputs
* Retry on failure
