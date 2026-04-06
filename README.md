# after-market-agent

## Backend

Run the API locally:

```bash
uvicorn backend.app.main:app --reload
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

Seed the default watchlist:

```bash
python -m backend.scripts.seed_watchlist
```
