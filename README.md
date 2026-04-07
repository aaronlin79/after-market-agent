# after-market-agent

## Backend

Run the API locally:

```bash
uvicorn backend.app.main:app --reload
```

Open the MVP UI at:

```text
http://127.0.0.1:8000/
```

Run migrations:

```bash
alembic upgrade head
```

Watchlist API endpoints are available under `/watchlists`.
Manual news ingestion is available at `POST /pipelines/news/run`.
SEC-only ingestion is available at `POST /pipelines/sec/run`.
Combined news + SEC ingestion is available at `POST /pipelines/full-ingest`.
Manual news clustering is available at `POST /pipelines/news/cluster`.
Digest generation is available at `POST /digests/generate`.
Digest send uses `POST /digests/{digest_id}/send` and defaults to the mock provider locally.
The full manual morning run is available at `POST /jobs/morning-run`.
Set `ENABLE_SCHEDULER=true` to enable the daily in-process scheduler.
Set `OPENAI_API_KEY` to enable OpenAI-backed cluster summaries; otherwise the baseline summarizer is used.
Set `NEWS_PROVIDER=mock` for local/offline development or `NEWS_PROVIDER=finnhub` with `NEWS_API_KEY` for real company news.
Set `SEC_USER_AGENT` before using SEC ingestion. `SEC_API_KEY` remains optional.
Admin inspection endpoints are available under `/admin`, including pipeline runs, source items, clusters, summaries, digests, and local evals.
Run local evaluations with `POST /admin/evals/run`.
Evaluation fixtures live under `backend/evals/fixtures/`; see `docs/EVALUATION.md`.

## MVP UI

The FastAPI app also serves a lightweight frontend for local use:

- Dashboard: latest digest, top ranked clusters, latest run status, and a `Run now` action
- Watchlists: create a watchlist, edit its name/description, add symbols, and remove symbols
- Runs & Status: inspect recent pipeline runs and recent success/failure state

The dashboard surfaces `Why it matters` for each digest item and highlights `Undercovered but Important` clusters when the backend marks them as high-importance with limited source coverage.

Seed the default watchlist:

```bash
python -m backend.scripts.seed_watchlist
```
