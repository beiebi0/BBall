# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Rules (from Rules.md — MUST follow)

1. **Read all `.md` files** in the project root before starting work (`Task.md`, `Master_Plan.md`, `README.md`, `User_journey.md`, `Implementation_plan.md`, `Rules.md`)
2. **Check `Task.md`** before writing code — only work on tracked tasks
3. **Write a test** after completing each task; task is not done until the test passes
4. **Update all `.md` files** after any code change to reflect what changed
5. **Documentation and code go in the same commit** — never commit one without the other

## Build & Run

```bash
# Start all services (FastAPI, Pub/Sub subscriber worker, Postgres, GCS emulator, Pub/Sub emulator)
cd backend && docker compose up --build

# Web client at http://localhost:8000 (redirects to /static/index.html)
# API available at http://localhost:8000
# Fake GCS server at http://localhost:4443
# Pub/Sub emulator at localhost:8085
# Health check: curl http://localhost:8000/health
```

## Database Migrations

```bash
cd backend && alembic upgrade head
```

Two migrations: `001_initial_schema.py` and `002_rename_s3_key_to_gcs_key.py`. Alembic uses the sync Postgres URL from `alembic.ini`.

## Running Tests

```bash
# Mocked unit tests (no external deps needed)
cd backend && python -m pytest pipeline/detection/test_rim_detector.py -v
cd backend && python -m pytest pipeline/test_detection_cache.py -v
cd backend && python -m pytest app/core/test_storage.py app/core/test_pubsub.py app/workers/test_subscriber.py -v

# Tests requiring YOLO weights (auto-downloaded on first run)
cd backend && python -m pytest pipeline/detection/test_player_detector.py -v
cd backend && python -m pytest pipeline/detection/test_ball_detector.py -v

# API integration tests (run against live backend — Docker Compose or GCP)
cd backend && API_BASE_URL=http://localhost:8000 python -m pytest tests/test_api_integration.py -v
# Or against GCP:
cd backend && API_BASE_URL=https://bball-api-XXXX.run.app python -m pytest tests/test_api_integration.py -v

# Manual integration tests (require pickup_game.mp4 in backend/)
cd backend && python test_pipeline.py
cd backend && python test_full_detection.py
```

No linter or formatter is configured.

## Architecture

**Basketball highlight video generator** — users upload game footage, the backend detects players/ball/rim, then generates personalized highlight reels.

### Stack

- **API**: FastAPI (async) + Uvicorn with hot-reload
- **Task queue**: GCP Pub/Sub with a pull-subscriber worker
- **DB**: PostgreSQL 16 with async SQLAlchemy (`asyncpg`) for API routes, sync SQLAlchemy for worker tasks
- **Storage**: Google Cloud Storage (GCS) with signed URL upload pattern (API never proxies video bytes); `fake-gcs-server` for local dev
- **ML**: YOLO11m (players + ball), YOLO11n-pose (zero-face ball filtering), Roboflow inference SDK (rim detection)
- **Video**: ffmpeg via `ClipExtractor` (stream-copy with re-encode fallback)

### Two-Phase Pub/Sub Pipeline

The processing pipeline splits at a user-interaction point:

1. **`process_video_detection`** — runs player/ball/rim detection + tracking → caches results to GCS (`detection_cache/{job_id}/frames.json`) → sets job to `awaiting_selection` → returns annotated frame so user can pick their player
2. **`process_video_highlights`** — triggered after player selection → loads cached detection data from GCS (falls back to full re-detection if missing) → event detection → clip extraction → uploads highlight reels to GCS

API routes publish messages to Pub/Sub topics; the subscriber worker (`app/workers/subscriber.py`) pulls messages from subscriptions and dispatches to task functions. Progress is reported via `PipelineOrchestrator` callbacks that update the job row, polled by `GET /jobs/{id}/progress`.

### Layer Separation

- **`app/`** — FastAPI routes, Pydantic schemas, SQLAlchemy ORM models, auth (JWT/bcrypt), GCS helpers
- **`pipeline/`** — ML/CV processing with pure Python `@dataclass` models (no web/DB coupling)
- **`app/workers/`** — Task functions + Pub/Sub subscriber that bridges API ↔ pipeline (use sync DB sessions)

### Key Design Details

- **Async API / Sync workers**: API routes use `async def` + `AsyncSession`; worker tasks use synchronous `create_engine` (subscriber runs in threads)
- **Zero-Face Policy**: Ball candidates within 30px of head keypoints (from pose model) are discarded as false positives
- **IQR rim filtering**: `RimDetector` samples ~10 frames, applies IQR outlier filtering, returns median bbox
- **`ROBOFLOW_API_KEY` is optional**: If unset, rim detection is skipped and event detection uses upper-quarter heuristic
- **Frame skipping**: `frame_skip=5` by default (~6 FPS from 30 FPS source). Uses YOLO's `vid_stride` to skip frames before inference — true 5x speedup. Configurable via `FRAME_SKIP` env var.
- **Job cancellation**: `POST /jobs/{id}/cancel` sets status to `cancelled`; worker checks on every progress callback and raises `JobCancelledError` to stop cleanly.
- **Settings singleton**: All config in `app/config.py` via `pydantic-settings`, reading from env vars / `.env`

### Status State Machines

```
Video:  uploading → uploaded → processing → done
Job:    queued → processing → awaiting_selection → processing → completed | failed | cancelled
```

### Database (5 tables)

`users`, `videos`, `jobs`, `events`, `highlights` — see `alembic/versions/001_initial_schema.py` for full schema.

## Environment Variables

Set in `docker-compose.yml` for containerized dev. For local dev, use `backend/.env`. Key vars:
- `DATABASE_URL` / `DATABASE_URL_SYNC` — async (asyncpg) and sync (psycopg2) Postgres URLs
- `GCS_BUCKET`, `GCS_PROJECT_ID`, `GCS_ENDPOINT_URL` (for fake-gcs-server), `GCS_SERVICE_ACCOUNT_JSON` (prod only)
- `PUBSUB_PROJECT_ID`, `PUBSUB_EMULATOR_HOST`, `PUBSUB_TOPIC_DETECTION`, `PUBSUB_TOPIC_HIGHLIGHTS`, `PUBSUB_SUBSCRIPTION_DETECTION`, `PUBSUB_SUBSCRIPTION_HIGHLIGHTS`
- `JWT_SECRET`, `ROBOFLOW_API_KEY` (optional), `FRAME_SKIP` (default 5)

## Web Client

A single-file SPA (`backend/static/index.html`) is served at `/static/index.html` (root `/` redirects there). It exercises the full backend flow: auth, upload, processing progress, player selection, and highlight viewing. No build tools needed. For local dev, GCS signed URLs are automatically fixed (replaces `fake-gcs-server` hostname with `localhost`).

## GCP Deployment

The backend is deployed to GCP Cloud Run. Key details:
- **API**: `bball-api` on Cloud Run (1 vCPU, 512 MB, scales to 0)
- **Worker**: `bball-worker` on Cloud Run (2 vCPU, 8 GB, min-instances=1, HTTP health server on port 8080)
- **Cloud SQL**: PostgreSQL 16, `db-f1-micro`, ENTERPRISE edition, public IP
- **GCS signed URLs**: Require SA key in Secret Manager (`gcs-sa-key` → `GCS_SERVICE_ACCOUNT_JSON` env var)
- **Deploy script**: `backend/deploy.sh` — idempotent, provisions all resources. Uses `--update-env-vars` for DB URLs (special chars break `--set-env-vars`).
- Worker uses deferred Pub/Sub init (background thread) so health probe passes before credential lookups complete
- Worker monitors streaming pull futures — logs errors and shuts down cleanly if a subscription fails

## Project Status

Phase 1 (backend) is deployed and verified on GCP. 12 integration tests pass against production. A web client exists for testing. Phase 2 (React Native iOS app) has not been started.
