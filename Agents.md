# AGENTS.md

## Project Purpose

This project builds an AI-powered system that ingests after-market financial news and SEC filings, ranks important developments for a watchlist, and generates a grounded morning digest.

The system prioritizes **reliability, clarity, and explainability** over complexity.

---

## Core Principles

* Correctness over cleverness
* Readability over abstraction
* Simplicity over over-engineering
* Explicit behavior over implicit assumptions
* Traceability across all pipeline stages

---

## Architecture Rules

* Strictly separate:

  * ingestion
  * normalization
  * clustering
  * ranking
  * summarization
  * delivery
* Never overwrite raw source data
* Store derived data separately
* All pipeline stages must be independently testable
* Avoid tight coupling between modules

---

## Coding Standards

* Use Python for backend services
* Use FastAPI for API layer (when implemented)
* Use type hints for all public functions
* Add docstrings for public classes and functions
* Keep functions small and focused
* Keep files under ~300–400 lines where possible
* Prefer explicit variable names over abbreviations

---

## LLM / Prompting Rules

* Always prefer structured outputs (JSON)
* Never fabricate financial facts
* Never assume market impact without explicit source support
* Always ground summaries in source data
* Include uncertainty where appropriate
* Do not include investment advice

---

## Database Rules

* Use migrations for schema changes
* Prefer additive schema evolution
* Preserve raw ingested data permanently
* Include timestamps on all key records
* Design for replayability and auditability

---

## Testing Requirements

* Every module must include tests
* Cover:

  * happy paths
  * edge cases
  * failure scenarios
* Do not skip tests unless explicitly unavoidable

---

## Logging & Observability

* Log each pipeline stage
* Include:

  * counts
  * durations
  * errors
* Do not silently fail
* Ensure failures are debuggable

---

## Performance & Cost Awareness

* Avoid unnecessary API calls
* Cache results where appropriate
* Do not summarize low-value or duplicate items
* Use lightweight models when possible for intermediate steps

---

## When Requirements Are Unclear

* Implement the simplest working solution
* Leave clear TODO comments
* Do NOT invent major new features
* Refer to PRODUCT_SPEC.md for intent

---

## Anti-Patterns to Avoid

* Over-engineering
* Premature optimization
* Hidden side effects
* Mixing business logic with API or DB layers
* Unstructured LLM outputs
* Silent data mutation
