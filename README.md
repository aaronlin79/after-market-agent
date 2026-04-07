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

Suggested first-run flow:

1. Open `http://127.0.0.1:8000/`
2. Go to `Watchlists` and create or edit a watchlist
3. Add at least one symbol
4. Return to `Dashboard` and click `Run now`
5. Review the latest digest and `Runs & Status`

Seed the default watchlist:

```bash
python -m backend.scripts.seed_watchlist
```

## Run Tonight

Minimum `.env` setup for a safe local MVP:

- `DATABASE_URL=sqlite:///./after_market_agent.db`
- `NEWS_PROVIDER=mock` for offline/local testing, or `NEWS_PROVIDER=finnhub` with `NEWS_API_KEY`
- `EMAIL_PROVIDER=mock` for local testing, or `EMAIL_PROVIDER=resend` with `EMAIL_API_KEY`
- `DIGEST_RECIPIENTS=you@example.com`
- `SEC_USER_AGENT=after-market-agent your-email@example.com` if you want SEC ingestion enabled
- `OPENAI_API_KEY=` to enable OpenAI summaries, otherwise baseline fallback is used
- `ENABLE_SCHEDULER=false` unless you intentionally want the overnight scheduler on

Tonight checklist:

1. Run migrations: `alembic upgrade head`
2. Start the app: `uvicorn backend.app.main:app --reload`
3. Open `http://127.0.0.1:8000/`
4. Create or update the watchlist and add at least one symbol
5. Click `Run now` on the dashboard
6. Confirm the latest digest appears and `Runs & Status` shows a successful or partial-success run
7. Optional smoke check: `python -m backend.scripts.smoke_check`

If you want to leave it overnight:

- keep `ENABLE_SCHEDULER=true`
- set `SCHEDULED_WATCHLIST_ID`
- use `EMAIL_PROVIDER=mock` for a dry run, or a configured real provider if you want delivery
- check the dashboard and `/admin/pipeline-runs` once before you leave it running
