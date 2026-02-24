# BBall Highlight Video Generator — Master Plan

## Overview

Build an iOS app that generates basketball highlight videos from pickup game recordings. Users upload a video from their camera roll, identify themselves in the video, and receive downloadable highlight reels.

## Key Decisions

- **Platform**: iOS app (React Native)
- **Processing**: Cloud backend (Python FastAPI + GCP Pub/Sub workers)
- **Highlights**: All key plays (scoring, assists, blocks, steals, rebounds, crossovers, fast breaks)
- **Player ID**: User picks team color + taps to select themselves in a frame
- **Output**: Single highlight reel per player + full game reel
- **Accounts**: Full user accounts + cloud storage for past highlights
- **MVP priority**: End-to-end pipeline working first, polish detection later

## Database Schema

5 tables: `users`, `videos`, `jobs`, `events`, `highlights`

- **users**: id, email, password_hash, display_name, timestamps
- **videos**: id, user_id (FK), s3_key, filename, duration_secs, resolution, status
- **jobs**: id, video_id (FK), user_id (FK), selected_player_track_id, team_color_hex, status, progress, stage, error_message
- **events**: id, job_id (FK), event_type, frame_start, frame_end, timestamps, player_track_id, confidence, metadata_json
- **highlights**: id, job_id (FK), highlight_type (game/player), player_track_id, s3_key, duration_secs, file_size_bytes

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/signup` | Create account |
| POST | `/auth/login` | Get JWT token |
| GET | `/auth/me` | Get current user |
| POST | `/videos/upload-url` | Get presigned S3 upload URL |
| POST | `/videos/{id}/confirm` | Confirm upload complete |
| GET | `/videos` | List user's videos |
| POST | `/jobs` | Start processing job |
| GET | `/jobs/{id}` | Get job status |
| GET | `/jobs/{id}/progress` | Lightweight progress polling |
| POST | `/jobs/{id}/select-player` | Submit player selection + team color |
| GET | `/highlights?job_id=X` | List generated highlight reels |
| GET | `/highlights/{id}` | Get highlight with download URL |
| GET | `/highlights/{id}/download` | Get presigned download URL |

## Processing Pipeline

```
Upload to GCS → Download to worker → Stage 1: Setup (0-10%)
→ Stage 2: Detection & Tracking per-frame (10-60%)
→ Stage 3: Event Detection (60-75%)
→ Stage 4: Clip Extraction via ffmpeg (75-90%)
→ Stage 5: Compile game + player reels (90-98%)
→ Stage 6: Upload reels to GCS, mark done (98-100%)
```

Two Pub/Sub-driven tasks split by the player selection step:
1. `process_video_detection` — Downloads video, detects rim position (Roboflow, optional), runs YOLO11 detection/tracking with pose-based ball filtering, extracts preview
2. `process_video_highlights` — Detects events (using rim proximity if available, upper-quarter fallback otherwise), extracts clips, compiles reels, uploads to GCS

## Phased Implementation

### Phase 1: Backend Core (Complete)

- Project scaffolding (Docker, FastAPI, requirements)
- DB models + Alembic migrations
- JWT auth system (signup/login/me)
- GCS signed URL upload flow (migrated from S3/MinIO)
- Prototype upgraded to YOLO11m + YOLO11n-pose (from YOLOv8n + custom ball model)
- Pose-based ball filtering to eliminate face/head false positives
- Pipeline modules refactored from possession_tracker.py
- MVP event detection (possession changes, potential scores, fast breaks)
- ffmpeg clip extraction + concatenation
- Pipeline orchestrator
- GCP Pub/Sub worker integration with progress updates (migrated from Celery/Redis)
- All API endpoints (jobs, highlights, player selection)

### Phase 2: iOS App (Next)

- React Native setup
- Auth screens (signup/login)
- Home screen (video history)
- Video upload (camera roll → presigned URL → S3)
- Player selection UI (tap player + pick team color)
- Job progress (polling progress bar)
- Highlight viewing (watch + download reels)

### Phase 3: Better Highlight Detection (Future)

- ~~Hoop/court detection for real scoring detection~~ — **Partially done**: rim detection via Roboflow model integrated; replaces upper-quarter heuristic with proximity-based scoring when `ROBOFLOW_API_KEY` is set
- Team color clustering (K-means on jersey HSV histograms)
- Shot detection (ball trajectory toward hoop)
- Advanced events: steals, blocks, assists, rebounds, crossovers
- Highlight quality ranking + configurable reel length
- Enable BotSORT Re-ID for better player identity persistence
- Tune pose-filtering distance threshold (currently 30px) per resolution

## Data Flow

```
Phone → POST /videos/upload-url → signed URL
Phone → PUT to GCS (direct upload)
Phone → POST /videos/confirm → triggers preview extraction
Phone → POST /jobs → publishes Pub/Sub message
Phone → GET /jobs/{id}/progress (poll 3s) → progress updates
Worker → runs full pipeline → uploads reels to GCS
Phone → GET /highlights → signed download URLs
Phone → stream/download highlight reels
```
