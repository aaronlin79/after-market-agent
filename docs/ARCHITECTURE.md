# Architecture

## Pipeline Overview

ingestion → normalization → clustering → ranking → summarization → digest assembly → delivery

---

## Modules

### Ingestion

Fetch data from:

* news APIs
* SEC filings

### Normalization

* clean text
* standardize timestamps
* map tickers
* canonicalize URLs

### Clustering

* group duplicate or related stories
* select representative source

### Ranking

* score importance
* prioritize watchlist relevance
* assign event types

### Summarization

* generate grounded summaries
* enforce structured outputs

### Digest Assembly

* organize into sections
* format output

### Delivery

* email digest
* future: Slack / UI

---

## Data Principles

* Store raw data
* Store derived data separately
* Preserve provenance
* Enable replay and debugging

---

## Design Philosophy

* modular
* testable
* observable
* simple
