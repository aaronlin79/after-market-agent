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
Manual news clustering is available at `POST /pipelines/news/cluster`.
Digest generation is available at `POST /digests/generate`.
Digest send uses `POST /digests/{digest_id}/send` and defaults to the mock provider locally.
The full manual morning run is available at `POST /jobs/morning-run`.
Set `ENABLE_SCHEDULER=true` to enable the daily in-process scheduler.

Seed the default watchlist:

```bash
python -m backend.scripts.seed_watchlist
```
