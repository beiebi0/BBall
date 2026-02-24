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

### Phase 1 Result

A fully functional backend ready to be consumed by a mobile client. The complete commit history:

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
| **Upload** | Camera roll picker + progress | `POST /videos/upload-url`, PUT to S3, `POST /videos/{id}/confirm` |
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
Pub/Sub Subscriber Worker (GPU)
    ├── Roboflow inference (rim detection, optional)
    ├── YOLO11m (player detection)
    ├── YOLO11m (ball detection, COCO class 32)
    ├── YOLO11n-pose (false-positive filtering)
    ├── BotSORT (multi-object tracking)
    └── ffmpeg (clip extraction + concatenation)
    ↕
Google Cloud Storage (videos + highlights)  ·  PostgreSQL (metadata)  ·  Pub/Sub (task queue)
```
