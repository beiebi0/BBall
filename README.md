# BBall Highlight Video Generator

An iOS app that generates basketball highlight videos from pickup game recordings. Upload a video, identify yourself, and receive downloadable highlight reels — one for the full game and one per player.

## Architecture

```
iOS App (React Native)
    ↕ REST API (JWT auth)
FastAPI Server
    ↕ Task queue
Celery Worker (GPU) ← YOLO models + ffmpeg
    ↕
AWS S3 (videos + highlights) + PostgreSQL (metadata + accounts) + Redis (task broker)
```

## Project Structure

```
BBall/
├── backend/
│   ├── app/                  # FastAPI application
│   │   ├── api/              # Route handlers (auth, videos, jobs, highlights)
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── core/             # Security, S3, database config
│   │   └── workers/          # Celery tasks
│   ├── pipeline/             # ML/Video processing pipeline
│   │   ├── detection/        # YOLOv8 player + ball detectors
│   │   ├── tracking/         # Ball possession tracking
│   │   ├── events/           # Game event detection
│   │   └── video/            # ffmpeg clip extraction
│   ├── models/               # YOLO weight files + tracker config (gitignored)
│   ├── alembic/              # Database migrations
│   ├── docker-compose.yml    # Local dev (Postgres + Redis + MinIO)
│   └── Dockerfile
├── mobile/                   # React Native iOS app (Phase 2)
├── possession_tracker.py     # Original prototype
└── botsort.yaml              # BotSORT tracker config
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| iOS App | React Native + TypeScript |
| Backend API | Python FastAPI |
| Task Queue | Celery + Redis |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Object Storage | AWS S3 (MinIO for local dev) |
| Auth | JWT (email + password) |
| Player Detection | YOLOv8 Nano + BotSORT |
| Ball Detection | Custom YOLO model |
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
- **Redis** at `localhost:6379`
- **MinIO** (S3) at `http://localhost:9000` (console at `http://localhost:9001`)

### Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### API Health Check

```bash
curl http://localhost:8000/health
```

## API Flow

1. `POST /auth/signup` — Create account, get JWT
2. `POST /videos/upload-url` — Get presigned S3 upload URL
3. Upload video directly to S3 via presigned URL
4. `POST /videos/{id}/confirm` — Confirm upload complete
5. `POST /jobs` — Start processing (queues Celery task)
6. `GET /jobs/{id}/progress` — Poll processing status (every 3s)
7. `POST /jobs/{id}/select-player` — Select player + team color
8. `GET /highlights?job_id=X` — Get highlight reel download URLs

## Processing Pipeline

```
Upload → Download to Worker → Detection & Tracking (YOLOv8 + BotSORT)
→ Event Detection (possession changes, potential scores, fast breaks)
→ Clip Extraction (ffmpeg) → Compile Reels → Upload to S3
```

### MVP Event Detection

- **Possession change** — Ball switches between players
- **Potential score** — Ball detected in upper quarter of frame
- **Fast break** — Ball moves >60% of frame width in <3 seconds

Events get 3s padding before + 2s after; overlapping events merge into single clips.
