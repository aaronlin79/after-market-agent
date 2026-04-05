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

Seed the default watchlist:

```bash
python -m backend.scripts.seed_watchlist
```
