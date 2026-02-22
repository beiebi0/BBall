# Implementation Plan

How the BBall development has evolved, what has been built, and what comes next.

---

## Starting Point: The Prototype

Development began with a single-file proof of concept (`possession_tracker.py`) — a YOLOv8n-based script that could detect players and a ball in a basketball video, track them with BotSORT, and determine ball possession. It proved the core idea was viable but had major limitations:

- Used a custom-trained ball detector that produced frequent false positives (detecting heads/faces as balls)
- No backend, no API, no user accounts — just a local script
- No clip extraction or highlight generation

---

## Phase 1: Backend Core — Complete

With the prototype validating feasibility, development moved to building a production backend that could serve a mobile app.

### Step 1 — Project Scaffolding

Set up the foundational infrastructure:

- **Docker Compose** stack: PostgreSQL 16, Redis 7, MinIO (local S3), API server, Celery worker
- **FastAPI** application skeleton with config management (`pydantic-settings`, `.env`)
- **Dockerfile** with Python 3.11, ffmpeg, and OpenCV dependencies
- **requirements.txt** pinning all dependencies

### Step 2 — Database & Auth

Built the data layer and authentication:

- **5 SQLAlchemy models**: `users`, `videos`, `jobs`, `events`, `highlights`
- **Alembic migration** (`001_initial_schema.py`) creating all tables with FKs and indexes
- **JWT auth system**: signup, login, `get_current_user` dependency
- Password hashing with bcrypt

### Step 3 — S3 Upload Flow

Implemented the video upload pipeline:

- **Presigned URL generation** — app requests upload URL, uploads directly to S3
- **Upload confirmation** — app confirms upload, video status moves to `uploaded`
- **Video listing** — user can see their uploaded videos
- Works with AWS S3 in production and MinIO locally

### Step 4 — Detection Pipeline Upgrade

Refactored the prototype into proper pipeline modules and upgraded the ML stack:

- **Player detection** (`pipeline/detection/player_detector.py`) — upgraded from YOLOv8n to **YOLO11m** for better accuracy
- **Ball detection** (`pipeline/detection/ball_detector.py`) — switched from custom model to **YOLO11m with COCO class 32** (sports ball), added **YOLO11n-pose filtering** to eliminate head/face false positives by checking proximity to keypoints
- **Possession tracking** (`pipeline/tracking/possession.py`) — temporal smoothing with 6/10-frame majority voting for stability
- **BotSORT config** (`botsort.yaml`) — tuned tracker parameters; Re-ID disabled for now

### Step 5 — Event Detection

Built MVP game event detection (`pipeline/events/event_detector.py`):

| Event Type | Detection Rule |
|---|---|
| Possession change | Ball switches between tracked players |
| Potential score | Ball detected in upper quarter of frame |
| Fast break | Ball moves >60% of frame width in <3 seconds |

Events get padded (3s before, 2s after) and overlapping clips are merged. Clips are filtered by player involvement for personal reels.

### Step 6 — Video Processing

Implemented clip extraction and reel compilation (`pipeline/video/clip_extractor.py`):

- **ffmpeg-based** clip cutting — tries fast stream copy first, falls back to re-encode
- **Concatenation** of clips into a single highlight reel
- Separate reels: full game highlights + personal (selected player) highlights

### Step 7 — Orchestrator & Celery Integration

Wired everything together:

- **Pipeline orchestrator** (`pipeline/orchestrator.py`) — runs the full detection pipeline with stage-based progress (0-100%)
- **Two Celery tasks** split at the player selection step:
  1. `process_video_detection` — downloads video from S3, runs detection/tracking, extracts preview frame, pauses at `awaiting_selection`
  2. `process_video_highlights` — after user selects their player, runs event detection, extracts clips, compiles reels, uploads to S3
- **Progress polling** via `GET /jobs/{id}/progress` with status, percentage, and stage description

### Step 8 — Remaining API Endpoints

Completed the full API surface:

- **Job management** — create job, get status, progress polling, player selection
- **Highlights** — list reels for a job, get individual highlight, presigned download URLs

### Phase 1 Result

A fully functional backend ready to be consumed by a mobile client. The complete commit history:

1. `189ea4a` — Initial commit: possession tracker prototype (YOLOv8)
2. `34eae12` — Upgrade tracker to YOLO11 + pose-based ball filtering
3. `2916ad8` — Add Phase 1 backend: FastAPI server, ML pipeline, and project docs

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

- **Hoop/court detection** for real scoring detection (replacing upper-quarter heuristic)
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
    ↕ Celery task queue (Redis broker)
Celery Worker (GPU)
    ├── YOLO11m (player detection)
    ├── YOLO11m (ball detection, COCO class 32)
    ├── YOLO11n-pose (false-positive filtering)
    ├── BotSORT (multi-object tracking)
    └── ffmpeg (clip extraction + concatenation)
    ↕
AWS S3 (videos + highlights)  ·  PostgreSQL (metadata)  ·  Redis (task state)
```
