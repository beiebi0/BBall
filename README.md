# BBall Highlight Video Generator

An iOS app that generates basketball highlight videos from pickup game recordings. Upload a video, identify yourself, and receive downloadable highlight reels — one for the full game and one per player.

## Architecture

```
iOS App (React Native)
    ↕ REST API (JWT auth)
FastAPI Server
    ↕ Pub/Sub messages
Worker (GPU) ← YOLO models + ffmpeg
    ↕
Google Cloud Storage (videos + highlights) + PostgreSQL (metadata + accounts) + Pub/Sub (task queue)
```

## Project Structure

```
BBall/
├── backend/
│   ├── app/                  # FastAPI application
│   │   ├── api/              # Route handlers (auth, videos, jobs, highlights)
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── core/             # Security, GCS storage, Pub/Sub, database config
│   │   └── workers/          # Pub/Sub subscriber + task functions
│   ├── pipeline/             # ML/Video processing pipeline
│   │   ├── detection/        # YOLO11 player + ball detectors (with pose-based filtering)
│   │   ├── tracking/         # Ball possession tracking
│   │   ├── events/           # Game event detection
│   │   └── video/            # ffmpeg clip extraction
│   ├── models/               # YOLO weight files + tracker config (gitignored)
│   ├── alembic/              # Database migrations
│   ├── docker-compose.yml    # Local dev (Postgres + fake-gcs-server + Pub/Sub emulator)
│   └── Dockerfile
└── mobile/                   # React Native iOS app (Phase 2)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| iOS App | React Native + TypeScript |
| Backend API | Python FastAPI |
| Task Queue | GCP Pub/Sub (emulator for local dev) |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Object Storage | Google Cloud Storage (fake-gcs-server for local dev) |
| Auth | JWT (email + password) |
| Player Detection | YOLO11m + BotSORT |
| Ball Detection | YOLO11m (COCO class 32) + YOLO11n-pose filtering |
| Rim Detection | Roboflow inference (`basketball-xil7x/1`), optional |
| Video Processing | ffmpeg |

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.11+

### Local Development

```bash
cd backend
docker-compose up
```

This starts:
- **API server** at `http://localhost:8000`
- **PostgreSQL** at `localhost:5432`
- **Fake GCS server** at `http://localhost:4443`
- **Pub/Sub emulator** at `localhost:8085`

### Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### API Health Check

```bash
curl http://localhost:8000/health
```

### Deploy to GCP

Deploy the backend to Cloud Run with managed Cloud SQL, GCS, and Pub/Sub:

```bash
cd backend
export GCP_PROJECT_ID="your-project-id"
export DB_PASSWORD="$(openssl rand -base64 24)"
export JWT_SECRET="$(openssl rand -base64 32)"
export ROBOFLOW_API_KEY=""  # optional
./deploy.sh
```

This creates all GCP resources (Cloud SQL, GCS bucket, Pub/Sub topics, secrets) and deploys two Cloud Run services:
- **bball-api** — FastAPI server (1 vCPU, 512 MB, scales to 0)
- **bball-worker** — Pub/Sub subscriber for ML processing (2 vCPU, 4 GB, always-on)

See `backend/deploy.sh` for details.

## API Flow

1. `POST /auth/signup` — Create account, get JWT
2. `POST /videos/upload-url` — Get signed GCS upload URL
3. Upload video directly to GCS via signed URL
4. `POST /videos/{id}/confirm` — Confirm upload complete
5. `POST /jobs` — Start processing (publishes Pub/Sub message)
6. `GET /jobs/{id}/progress` — Poll processing status (every 3s)
7. `POST /jobs/{id}/select-player` — Select player + team color
8. `GET /highlights?job_id=X` — Get highlight reel download URLs

## Processing Pipeline

```
Upload → Download to Worker → Rim Detection (Roboflow, sampled frames)
→ Detection & Tracking (YOLO11m + BotSORT)
→ Pose-based Ball Filtering (YOLO11n-pose, discard face false positives)
→ Event Detection (possession changes, potential scores, fast breaks)
→ Clip Extraction (ffmpeg) → Compile Reels → Upload to GCS
```

### Detection Details

- **Player detection**: YOLO11m (COCO class 0) with BotSORT tracking at 1280px input resolution
- **Ball detection**: YOLO11m (COCO class 32, "sports ball") — unified model replaces the separate custom ball detector
- **Pose-based filtering**: YOLO11n-pose extracts head keypoints (nose, eyes, ears); ball candidates within 30px of any head keypoint are discarded as false positives
- **Rim detection**: Roboflow model (`basketball-xil7x/1`) samples ~10 evenly-spaced frames, filters outliers via IQR, and returns a stable median bounding box. Since the rim is static in fixed-camera footage, this adds near-zero overhead. Requires `ROBOFLOW_API_KEY` env var; when unset, falls back to the upper-quarter heuristic.
- **Possession stability**: Requires 6/10 frame majority (up from simple majority) for smoother tracking

### MVP Event Detection

- **Possession change** — Ball switches between players
- **Potential score** — If rim is detected: ball within 1.5x expanded rim zone (confidence 0.8/0.6). Fallback: ball in upper quarter of frame (confidence 0.5/0.3). Events include `detection_method` in metadata (`rim_proximity` or `upper_quarter`).
- **Fast break** — Ball moves >60% of frame width in <3 seconds

Events get 3s padding before + 2s after; overlapping events merge into single clips.
