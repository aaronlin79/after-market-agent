# Evaluation

## Scope

Local evaluation fixtures currently validate:

- clustering grouping sanity
- event classification accuracy
- ranking ordering sanity
- summary grounding sanity

## Non-Goals

These fixtures do not yet measure:

- market impact prediction
- financial correctness beyond the fixture content
- real-provider recall/coverage over live market data

## Extending

Add fixture examples to:

- `backend/evals/fixtures/core_eval_fixture.json`

Then update:

- `backend/evals/evaluation_runner.py`

Keep fixtures deterministic and small enough to run locally without network access.
