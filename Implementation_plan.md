# Implementation Plan

How the BBall development has evolved, what has been built, and what comes next.

---

## Starting Point: The Prototype

Development began with a single-file proof of concept (`possession_tracker.py`, since removed) — a YOLOv8n-based script that could detect players and a ball in a basketball video, track them with BotSORT, and determine ball possession. It proved the core idea was viable but had major limitations:

- Used a custom-trained ball detector that produced frequent false positives (detecting heads/faces as balls)
- No backend, no API, no user accounts — just a local script
- No clip extraction or highlight generation

---

## Phase 1: Backend Core — Complete

With the prototype validating feasibility, development moved to building a production backend that could serve a mobile app.

### Step 1 — Project Scaffolding

Set up the foundational infrastructure:

- **Docker Compose** stack: PostgreSQL 16, fake-gcs-server, Pub/Sub emulator, API server, Pub/Sub subscriber worker
- **FastAPI** application skeleton with config management (`pydantic-settings`, `.env`)
- **Dockerfile** with Python 3.11, ffmpeg, and OpenCV dependencies
- **requirements.txt** pinning all dependencies

### Step 2 — Database & Auth

Built the data layer and authentication:

- **5 SQLAlchemy models**: `users`, `videos`, `jobs`, `events`, `highlights`
- **Alembic migration** (`001_initial_schema.py`) creating all tables with FKs and indexes
- **JWT auth system**: signup, login, `get_current_user` dependency
- Password hashing with bcrypt

### Step 3 — GCS Upload Flow

Implemented the video upload pipeline:

- **Signed URL generation** — app requests upload URL, uploads directly to GCS
- **Upload confirmation** — app confirms upload, video status moves to `uploaded`
- **Video listing** — user can see their uploaded videos
- Works with Google Cloud Storage in production and fake-gcs-server locally

### Step 4 — Detection Pipeline Upgrade

Refactored the prototype into proper pipeline modules and upgraded the ML stack:

- **Player detection** (`pipeline/detection/player_detector.py`) — upgraded from YOLOv8n to **YOLO11m** for better accuracy
- **Ball detection** (`pipeline/detection/ball_detector.py`) — switched from custom model to **YOLO11m with COCO class 32** (sports ball), added **YOLO11n-pose filtering** to eliminate head/face false positives by checking proximity to keypoints
- **Possession tracking** (`pipeline/tracking/possession.py`) — temporal smoothing with 6/10-frame majority voting for stability
- **BotSORT config** (`backend/models/botsort.yaml`) — tuned tracker parameters; Re-ID disabled for now

### Step 5 — Event Detection

Built MVP game event detection (`pipeline/events/event_detector.py`):

| Event Type | Detection Rule |
|---|---|
| Possession change | Ball switches between tracked players |
| Potential score | Ball near detected rim (1.5x expanded zone, confidence 0.8/0.6) or in upper quarter of frame as fallback (confidence 0.5/0.3) |
| Fast break | Ball moves >60% of frame width in <3 seconds |

Events get padded (3s before, 2s after) and overlapping clips are merged. Clips are filtered by player involvement for personal reels. Each potential score event includes `detection_method` in metadata (`rim_proximity` or `upper_quarter`).

### Step 6 — Video Processing

Implemented clip extraction and reel compilation (`pipeline/video/clip_extractor.py`):

- **ffmpeg-based** clip cutting — tries fast stream copy first, falls back to re-encode
- **Concatenation** of clips into a single highlight reel
- Separate reels: full game highlights + personal (selected player) highlights

### Step 7 — Orchestrator & Pub/Sub Integration

Wired everything together:

- **Pipeline orchestrator** (`pipeline/orchestrator.py`) — runs the full detection pipeline with stage-based progress (0-100%), including optional rim detection at startup
- **Two Pub/Sub-driven tasks** split at the player selection step:
  1. `process_video_detection` — downloads video from GCS, detects rim position (if Roboflow API key set), runs detection/tracking, extracts preview frame, pauses at `awaiting_selection`
  2. `process_video_highlights` — after user selects their player, runs event detection (rim-based or fallback), extracts clips, compiles reels, uploads to GCS
- **Pub/Sub subscriber** (`app/workers/subscriber.py`) — pull subscriber that dispatches messages to task functions with ack/nack on success/failure
- **Progress polling** via `GET /jobs/{id}/progress` with status, percentage, and stage description

### Step 8 — Remaining API Endpoints

Completed the full API surface:

- **Job management** — create job, get status, progress polling, player selection
- **Highlights** — list reels for a job, get individual highlight, presigned download URLs

### Step 9 — Rim Detection Integration

Added Roboflow-based rim detection (`pipeline/detection/rim_detector.py`) to replace the naive upper-quarter heuristic for potential score events:

- **RimDetector** class samples ~10 evenly-spaced frames (skipping first/last 5%), runs Roboflow `basketball-xil7x/1` model, filters outlier detections via IQR on center coordinates, and returns a stable median bounding box
- **Orchestrator** runs rim detection before the main detection loop (at 8% progress), stores the result, and passes it to `EventDetector`
- **EventDetector** dispatches `_detect_potential_scores()` to either rim proximity scoring (ball within 1.5x expanded rim zone) or the original upper-quarter fallback
- **Config** adds `roboflow_api_key`, `rim_model_id`, `rim_conf_threshold`, `rim_num_samples` settings
- **Graceful fallback**: no API key → skip rim detection; no detections or inference failure → fall back to upper-quarter heuristic
- **Unit tests** (`pipeline/detection/test_rim_detector.py`) — 15 tests covering IQR filtering, stable position computation, single-frame detection, and end-to-end `detect_from_samples` with mocked video/model

### Step 10 — Docker Compose Fixes

Resolved several issues that would prevent the Docker stack from starting:

- **`.dockerignore`** — excludes `venv/`, `__pycache__/`, `.env`, and `*.pt` files from the Docker build context (saves 200MB+)
- **Model path defaults** — `config.py` and `orchestrator.py` defaults changed from `models/yolov8n.pt` / `models/ball_detector_model.pt` to `yolo11m.pt` / `yolo11n-pose.pt` (ultralytics auto-downloads standard models)
- **`pose_model_path` config** — added to `Settings`, `PipelineOrchestrator`, and both task instantiations so the pose model path is configurable end-to-end
- **`ROBOFLOW_API_KEY`** — passed through to `api` and `worker` services in `docker-compose.yml` (defaults to empty string for graceful fallback)

### Step 11 — Migrate from S3 + Celery/Redis to GCS + Pub/Sub

Replaced AWS-centric infrastructure with Google Cloud equivalents:

- **Storage**: Removed `boto3`, added `google-cloud-storage`. New `app/core/storage.py` replaces `app/core/s3.py` with same function signatures (signed upload/download URLs, upload_file, download_file). Supports `fake-gcs-server` for local dev via `GCS_ENDPOINT_URL`.
- **Task queue**: Removed `celery[redis]` + `redis`, added `google-cloud-pubsub`. New `app/core/pubsub.py` publishes messages to detection/highlights topics. New `app/workers/subscriber.py` is a pull-subscriber that dispatches to task functions with ack/nack.
- **Worker tasks**: Removed Celery decorators and `celery_app.py`; task functions are now plain Python functions called by the subscriber.
- **Docker Compose**: Removed `redis`, `minio`, `createbucket` services. Added `fake-gcs-server`, `pubsub-emulator`, `create-gcs-bucket`, `setup-pubsub` init containers.
- **Config**: Replaced S3/Redis env vars with GCS/Pub/Sub vars in `config.py`, `.env`, and `docker-compose.yml`.
- **Tests**: Added `test_storage.py`, `test_pubsub.py`, `test_subscriber.py` with mocked GCS/Pub/Sub clients.

### Step 12 — GCP Deployment

Created deployment infrastructure for running the backend on GCP Cloud Run with managed services:

- **`deploy.sh`** — Full gcloud CLI script that provisions all GCP resources: Artifact Registry, Cloud SQL (PostgreSQL 16), GCS bucket, Pub/Sub topics/subscriptions, Secret Manager secrets, service account with IAM roles, and two Cloud Run services (API + Worker). Runs Alembic migrations via a Cloud Run Job.
- **Config defaults** — Changed `gcs_endpoint_url`, `pubsub_emulator_host`, `gcs_project_id`, `pubsub_project_id` defaults to empty strings so production uses real GCP services via Application Default Credentials. Docker Compose still sets these explicitly for local dev.
- **CORS** — Made CORS origins configurable via `cors_origins` setting (comma-separated, defaults to `"*"` for dev).
- **Alembic env override** — `env.py` now reads `DATABASE_URL_SYNC` from environment to override `alembic.ini` URL, enabling Cloud SQL migrations without editing config files.
- **Same image, two services** — API uses default Dockerfile CMD (`uvicorn`); Worker overrides via Cloud Run `--command` flag. Worker runs with `--no-cpu-throttling` and `min-instances=1` since the pull subscriber must be always-on.

### Step 13 — Detection Cache Between Phases

Eliminated redundant detection in the two-phase pipeline. Previously, Phase 2 (`process_video_highlights`) re-ran the entire detection pipeline from scratch — re-loading all YOLO models and re-processing every frame — because Phase 1 results were discarded. For a 5-minute video at 30fps, this meant ~27,000 redundant DNN inferences.

**Fix:**
- **Serialization** — Added `to_dict()`/`from_dict()` methods to `BoundingBox`, `PlayerDetection`, and `FrameData` dataclasses, plus top-level `serialize_detection_cache()`/`deserialize_detection_cache()` functions in `pipeline/models.py`
- **Phase 1 caching** — After `run_detection()`, the worker serializes the `FrameData` list + rim position to JSON and uploads to GCS at `detection_cache/{job_id}/frames.json`
- **Phase 2 cache loading** — Worker downloads the cache, deserializes it, and calls the new `orchestrator.run_highlights_from_cache()` which skips straight to event detection + clip extraction. Falls back to `run_full_pipeline()` if cache is missing.
- **Tests** — 7 unit tests covering serialization round-trips and verifying the cache path skips `run_detection()`

### Step 14 — Production Deployment & Verification

Deployed and verified the full backend on GCP:

- **Cloud Run API** (`bball-api`) — 1 vCPU, 512 MB, scales to zero, public endpoint with `--allow-unauthenticated`
- **Cloud Run Worker** (`bball-worker`) — 2 vCPU, 8 GB, always-on (`min-instances=1`, `--no-cpu-throttling`), HTTP health server on port 8080 for startup probes
- **Cloud SQL** — PostgreSQL 16, `db-f1-micro` (ENTERPRISE edition), public IP with authorized networks
- **GCS** — `bball-videos-{project_id}` bucket with signed URLs via SA key in Secret Manager
- **Pub/Sub** — `video-detection` and `video-highlights` topics with 600s ack deadline subscriptions

Key deployment lessons incorporated into `deploy.sh`:
- Worker needs an HTTP health endpoint — Cloud Run startup probes require it. Added `_HealthHandler` to `subscriber.py` with deferred Pub/Sub init in a background thread.
- GCS signed URLs require a private key — Cloud Run's ADC doesn't include one. Solution: create SA key JSON, store in Secret Manager as `gcs-sa-key`, mount as `GCS_SERVICE_ACCOUNT_JSON` env var.
- Cloud SQL connections use public IP directly (not Unix socket) with `?ssl=disable` for asyncpg.
- Cloud Run Jobs use `--set-cloudsql-instances` (not `--add-cloudsql-instances`) and need `PYTHONPATH=/app` for Alembic.
- All gcloud commands need `--quiet` to prevent interactive prompts from hanging scripts.

### Step 15 — Integration Test Suite

Created `tests/test_api_integration.py` — 12 tests that run against a live backend (Docker Compose or GCP):

- **Health**: health check endpoint
- **Auth** (5 tests): signup, login, wrong password, get current user, no token, duplicate signup
- **Videos** (3 tests): get signed upload URL, list videos, upload URL without auth
- **Jobs** (1 test): create job with invalid video ID
- **Highlights** (1 test): list highlights for non-existent job

Run with: `API_BASE_URL=https://bball-api-XXXX.run.app python -m pytest tests/test_api_integration.py -v`

All 12 tests passing against the production GCP deployment.

### Step 16 — Rename S3 References to GCS

Replaced all remaining AWS S3 naming conventions with GCS equivalents:

- **DB columns**: `s3_key` → `gcs_key` in `videos` and `highlights` tables
- **Alembic migration 002** (`002_rename_s3_key_to_gcs_key.py`) — `ALTER COLUMN` rename, reversible
- **ORM models**: `Video.s3_key` → `Video.gcs_key`, `Highlight.s3_key` → `Highlight.gcs_key`
- **Schema**: `UploadURLResponse.s3_key` → `UploadURLResponse.gcs_key`
- **Storage functions**: `generate_presigned_upload_url` → `generate_signed_upload_url`, `generate_presigned_download_url` → `generate_signed_download_url`, all `s3_key` params → `gcs_key`
- **All callers** updated across `videos.py`, `highlights.py`, `jobs.py`, `tasks.py`

### Step 17 — Production Deployment Debugging

Deployed latest code to GCP and resolved several production issues:

- **Empty `GCS_BUCKET` env var** — The `+` character in the DB password broke `--set-env-vars` parsing, causing `GCS_BUCKET` to be empty. Fixed with `--update-env-vars`.
- **GCS signed URL auth failure** — Cloud Run's default compute credentials can't sign URLs. Required mounting the `gcs-sa-key` secret as `GCS_SERVICE_ACCOUNT_JSON` on both API and worker services.
- **GCS bucket didn't exist** — The bucket `bball-videos-{project_id}` was never created. Created with `gsutil mb`.
- **GCS CORS policy** — Browser PUT uploads to signed URLs were blocked. Fixed by setting CORS config (`PUT`, `GET`, `HEAD` from `*`) on the bucket.
- **Pub/Sub topics missing** — Topics `video-detection` and `video-highlights` with subscriptions were not created. Created manually.
- **Stale test data** — Integration tests (`test_api_integration.py`) were creating randomized `test-{uuid}@test.com` users and orphaned video rows on every run against production. Cleaned up with SQL deletes.

**Deployment cheat sheet** (code-only redeploy from Cloud Shell):

```bash
# ── Step 0: Set env vars (run once per Cloud Shell session) ──
export PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"
export REGION="us-central1"
export DB_PASSWORD="7Q3jnBHC+RjywqdWPrbfZGz2M9fXCzyx"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/bball-repo/bball:latest"
export SA_EMAIL="bball-sa@${PROJECT_ID}.iam.gserviceaccount.com"
export SQL_INSTANCE="bball-db"
export SQL_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
export PUBLIC_IP=$(gcloud sql instances describe "${SQL_INSTANCE}" --project="${PROJECT_ID}" --format="value(ipAddresses[0].ipAddress)")
export GCS_BUCKET="bball-videos-${PROJECT_ID}"
export DB_URL_ASYNC="postgresql+asyncpg://bball:${DB_PASSWORD}@${PUBLIC_IP}/bball?ssl=disable"
export DB_URL_SYNC="postgresql://bball:${DB_PASSWORD}@${PUBLIC_IP}/bball"
export SECRETS_FLAG="JWT_SECRET=jwt-secret:latest,GCS_SERVICE_ACCOUNT_JSON=gcs-sa-key:latest"

# ── Step 1: Pull latest code & build image ──
# First cd to the backend/ directory if not already there:
#   cd ~/BBall/backend
git pull
gcloud builds submit --tag "${IMAGE}" . --quiet

# ── Step 2: Deploy API ──
SIMPLE_ENV="GCS_BUCKET=${GCS_BUCKET}"
SIMPLE_ENV+=",GCS_PROJECT_ID=${PROJECT_ID}"
SIMPLE_ENV+=",GCS_ENDPOINT_URL="
SIMPLE_ENV+=",PUBSUB_PROJECT_ID=${PROJECT_ID}"
SIMPLE_ENV+=",PUBSUB_EMULATOR_HOST="
SIMPLE_ENV+=",PUBSUB_TOPIC_DETECTION=video-detection"
SIMPLE_ENV+=",PUBSUB_TOPIC_HIGHLIGHTS=video-highlights"

gcloud run deploy bball-api \
  --image="${IMAGE}" --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION}" \
  --set-env-vars="${SIMPLE_ENV}" \
  --set-secrets="${SECRETS_FLAG}" \
  --port=8000 --memory=512Mi --cpu=1 \
  --min-instances=0 --max-instances=10 \
  --allow-unauthenticated \
  --project="${PROJECT_ID}" --quiet

gcloud run services update bball-api --region="${REGION}" --project="${PROJECT_ID}" --quiet \
  --update-env-vars="DATABASE_URL=${DB_URL_ASYNC}"
gcloud run services update bball-api --region="${REGION}" --project="${PROJECT_ID}" --quiet \
  --update-env-vars="DATABASE_URL_SYNC=${DB_URL_SYNC}"

# ── Step 3: Deploy Worker ──
WORKER_SIMPLE_ENV="GCS_BUCKET=${GCS_BUCKET}"
WORKER_SIMPLE_ENV+=",GCS_PROJECT_ID=${PROJECT_ID}"
WORKER_SIMPLE_ENV+=",GCS_ENDPOINT_URL="
WORKER_SIMPLE_ENV+=",PUBSUB_PROJECT_ID=${PROJECT_ID}"
WORKER_SIMPLE_ENV+=",PUBSUB_EMULATOR_HOST="
WORKER_SIMPLE_ENV+=",PUBSUB_TOPIC_DETECTION=video-detection"
WORKER_SIMPLE_ENV+=",PUBSUB_TOPIC_HIGHLIGHTS=video-highlights"
WORKER_SIMPLE_ENV+=",PUBSUB_SUBSCRIPTION_DETECTION=video-detection-sub"
WORKER_SIMPLE_ENV+=",PUBSUB_SUBSCRIPTION_HIGHLIGHTS=video-highlights-sub"

gcloud run deploy bball-worker \
  --image="${IMAGE}" --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION}" \
  --command="python","-m","app.workers.subscriber" \
  --set-env-vars="${WORKER_SIMPLE_ENV}" \
  --set-secrets="${SECRETS_FLAG}" \
  --port=8080 --memory=8Gi --cpu=2 \
  --min-instances=1 --max-instances=3 \
  --timeout=3600 \
  --no-allow-unauthenticated --no-cpu-throttling \
  --project="${PROJECT_ID}" --quiet

gcloud run services update bball-worker --region="${REGION}" --project="${PROJECT_ID}" --quiet \
  --update-env-vars="DATABASE_URL=${DB_URL_ASYNC}"
gcloud run services update bball-worker --region="${REGION}" --project="${PROJECT_ID}" --quiet \
  --update-env-vars="DATABASE_URL_SYNC=${DB_URL_SYNC}"

# ── Step 4: Run migrations (only if DB schema changed) ──
gcloud run jobs execute bball-migrate --region="${REGION}" --project="${PROJECT_ID}" --wait --quiet

# ── Step 5: Verify ──
gcloud run services logs read bball-api --region="${REGION}" --limit=10
gcloud run services logs read bball-worker --region="${REGION}" --limit=20
```

### Step 18 — Deploy Script Env Var Fix & Worker Reliability

Fixed critical deployment issues discovered during production debugging:

- **`deploy.sh` env var parsing** — DB URLs (containing `://`, `@`, `+`, `=`) broke `--set-env-vars` comma-separated parsing. Fixed by deploying simple vars with `--set-env-vars` first, then patching DB URLs individually with `--update-env-vars`.
- **Streaming pull monitoring** — Added `_watch_future()` threads in `subscriber.py` that monitor Pub/Sub streaming pull futures. If a subscription fails (e.g., permission denied, not found), the error is logged and the worker shuts down cleanly instead of hanging silently.
- **Worker memory** — Bumped from 4 GiB to 8 GiB. YOLO11m model loading + per-frame inference exceeded the 4 GiB limit, causing OOM kills on Cloud Run.

### Step 19 — Frame Skipping & Job Cancellation

Reduced processing cost and added operational controls:

- **Frame skipping** — New `frame_skip` config setting (default `5`, ~6 FPS from 30 FPS source). The YOLO tracker still streams all frames, but ball detection + possession tracking only runs on every Nth frame. Reduces memory (~5x fewer `FrameData` objects stored) and processing time. Configurable via `FRAME_SKIP` env var.
- **Job cancellation** — New `POST /jobs/{id}/cancel` endpoint sets job status to `cancelled`. Worker checks `job.status` in the DB on every progress callback; if cancelled, raises `JobCancelledError` which cleanly stops processing and acks the Pub/Sub message. Works for both detection and highlights phases.

### Phase 1 Result

A fully functional backend deployed and verified on GCP, ready to be consumed by a mobile app. The complete commit history:

1. `189ea4a` — Initial commit: possession tracker prototype (YOLOv8)
2. `34eae12` — Upgrade tracker to YOLO11 + pose-based ball filtering
3. `2916ad8` — Add Phase 1 backend: FastAPI server, ML pipeline, and project docs
4. `a4fabbd` — Integrate YOLO11m and Zero-Face filtering into backend pipeline code
5. `2a64708` — Remove obsolete `possession_tracker.py` prototype
6. `915c939` — Remove redundant root `botsort.yaml` (kept in `backend/models/`)

---

## Phase 2: iOS App — Next

Build the React Native iOS app that consumes the backend API. The screens map directly to the user journey:

| Screen | Purpose | API Calls |
|---|---|---|
| **Auth** (signup/login) | Account creation and login | `POST /auth/signup`, `POST /auth/login` |
| **Home** | Video history + upload button | `GET /videos` |
| **Upload** | Camera roll picker + progress | `POST /videos/upload-url`, PUT to GCS, `POST /videos/{id}/confirm` |
| **Player Selection** | Tap on annotated frame to identify self | `POST /jobs/{id}/select-player` |
| **Processing** | Progress bar while pipeline runs | `GET /jobs/{id}/progress` (poll every 3s) |
| **Highlights** | Watch + download/share reels | `GET /highlights?job_id=X`, `GET /highlights/{id}/download` |

Tech stack: React Native + TypeScript, Expo for dev tooling, standard iOS camera roll permissions.

---

## Phase 3: Better Highlight Detection — Future

Improvements to detection accuracy and event coverage once the end-to-end MVP is working:

- ~~**Hoop/court detection** for real scoring detection (replacing upper-quarter heuristic)~~ — **Done**: rim detection via Roboflow model integrated (Step 9)
- **Team color clustering** via K-means on jersey HSV histograms
- **Shot detection** tracking ball trajectory toward the hoop
- **Advanced events**: steals, blocks, assists, rebounds, crossovers
- **Highlight ranking** to surface the best clips and allow configurable reel length
- **BotSORT Re-ID** for stronger player identity persistence across occlusions
- **Resolution-adaptive thresholds** for pose-filtering distance (currently hardcoded at 30px)

---

## Architecture Reference

```
React Native iOS App
    ↕ REST API (JWT auth)
FastAPI Server (uvicorn)
    ↕ Pub/Sub messages
Pub/Sub Subscriber Worker (CPU, Cloud Run)
    ├── Roboflow inference (rim detection, optional)
    ├── YOLO11m (player detection)
    ├── YOLO11m (ball detection, COCO class 32)
    ├── YOLO11n-pose (false-positive filtering)
    ├── BotSORT (multi-object tracking)
    └── ffmpeg (clip extraction + concatenation)
    ↕
Google Cloud Storage (videos + highlights)  ·  PostgreSQL (metadata)  ·  Pub/Sub (task queue)
```
