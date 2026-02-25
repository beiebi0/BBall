# Tasks

## Completed

- [x] Prototype possession tracker (YOLOv8 + BotSORT)
- [x] Upgrade detection to YOLO11m + pose-based ball filtering
- [x] Project scaffolding (Docker Compose, FastAPI, Dockerfile, requirements.txt)
- [x] Database models + Alembic migration (users, videos, jobs, events, highlights)
- [x] JWT authentication (signup, login, get current user)
- [x] S3 presigned URL upload flow (upload-url, confirm, list videos) — **migrated to GCS signed URLs**
- [x] Player detection module (YOLO11m + BotSORT)
- [x] Ball detection module (YOLO11m COCO class 32 + YOLO11n-pose filtering)
- [x] Possession tracking with temporal smoothing (6/10 majority)
- [x] MVP event detection (possession changes, potential scores, fast breaks)
- [x] ffmpeg clip extraction + reel concatenation
- [x] Pipeline orchestrator with progress stages (0-100%)
- [x] Celery tasks (process_video_detection, process_video_highlights) — **migrated to GCP Pub/Sub**
- [x] Jobs API (create, status, progress polling, player selection)
- [x] Highlights API (list, get, download)
- [x] Project docs (README, Master_Plan, User_journey, Implementation_plan, Task, Rules)
- [x] Integrate YOLO11m + Zero-Face filtering into pipeline code (player_detector, ball_detector)
- [x] Add unit tests for detection modules (test_ball_detector, test_player_detector)
- [x] Remove obsolete prototype (`possession_tracker.py`) and redundant root `botsort.yaml`
- [x] Integrate Roboflow rim detection (`RimDetector`, orchestrator wiring, rim-proximity scoring in `EventDetector`, config settings, task plumbing)
- [x] Add unit tests for RimDetector (test_rim_detector.py — 15 tests)
- [x] Fix Docker Compose stack for first run (`.dockerignore`, model path defaults, `ROBOFLOW_API_KEY` env, `pose_model_path` wiring)
- [x] Migrate from AWS S3 + Celery/Redis to GCS + Pub/Sub (storage, task queue, Docker Compose, tests, docs)

- [x] GCP deployment script (`deploy.sh`) — Cloud Run (API + Worker), Cloud SQL, GCS, Pub/Sub, Secret Manager, Artifact Registry
- [x] Production-ready config defaults (empty strings for emulator/endpoint vars so prod uses real GCP services)
- [x] Configurable CORS origins via `cors_origins` setting
- [x] Alembic env var override for Cloud SQL migrations (`DATABASE_URL_SYNC`)
- [x] Deploy backend to GCP — API + Worker on Cloud Run, Cloud SQL, GCS, Pub/Sub all verified working
- [x] Worker health server for Cloud Run startup probe (HTTP endpoint on port 8080, deferred Pub/Sub init)
- [x] GCS signed URLs via SA key in Secret Manager (`gcs-sa-key` secret, `GCS_SERVICE_ACCOUNT_JSON` env var)
- [x] API integration test suite (`tests/test_api_integration.py` — 12 tests, all passing against GCP)

- [x] Web client (`backend/static/index.html`) — single-file SPA for auth, upload, processing, player selection, and highlight viewing
- [x] Annotated preview endpoint (`GET /jobs/{id}/preview`) — returns preview image URL + player list from detection
- [x] `PipelineOrchestrator.extract_annotated_preview()` — draws green bounding boxes + track IDs on detected players
- [x] Worker produces `players.json` alongside annotated preview during detection phase
- [x] Static file serving in FastAPI (`/static`, root redirect to `/static/index.html`)
- [x] Detection cache between pipeline phases — Phase 1 serializes `FrameData` + rim position to GCS; Phase 2 loads cache and skips re-detection (eliminates ~50% redundant YOLO inference)
- [x] Rename all S3 references to GCS (`s3_key` → `gcs_key`, `presigned` → `signed`) + Alembic migration 002
- [x] Install local venv dependencies (`pydantic-settings`, `google-cloud-storage`, `google-cloud-pubsub`) so unit tests run locally
- [x] GCS bucket CORS configuration for browser-based signed URL uploads
- [x] Pub/Sub topics and subscriptions created in production

## Next Steps

### Production E2E Testing (In Progress)

Backend is deployed to GCP. Auth, upload, and job creation are verified working. Remaining:

- [x] Auth flow: signup → login → token works on protected routes
- [x] Upload flow: get signed URL → upload video to GCS → confirm
- [x] Job creation: create job → Pub/Sub message published
- [ ] Worker picks up detection job and runs YOLO pipeline
- [ ] Detection completes → job status moves to `awaiting_selection`
- [ ] Player selection → highlight generation kicks off
- [ ] Highlights uploaded to GCS and download URLs work
- [ ] Full end-to-end flow verified

### Phase 2: iOS App

- [ ] React Native + TypeScript project setup
- [ ] Auth screens (signup / login)
- [ ] Home screen (upload button + video history)
- [ ] Video upload (camera roll picker → signed URL → GCS → confirm)
- [ ] Player selection UI (annotated frame, tap to select)
- [ ] Processing screen (progress bar polling /jobs/{id}/progress)
- [ ] Highlights screen (watch + download/share reels)

### Phase 3: Better Detection (Future)

- [x] ~~Hoop/court detection for real scoring~~ — Rim detection via Roboflow integrated
- [ ] Team color clustering (K-means on jersey HSV)
- [ ] Shot detection (ball trajectory toward hoop)
- [ ] Advanced events (steals, blocks, assists, rebounds, crossovers)
- [ ] Highlight ranking + configurable reel length
- [ ] Enable BotSORT Re-ID
- [ ] Resolution-adaptive pose-filtering thresholds
