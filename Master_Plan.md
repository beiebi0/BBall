# BBall Highlight Video Generator — Master Plan

## Overview

Build an iOS app that generates basketball highlight videos from pickup game recordings. Users upload a video from their camera roll, identify themselves in the video, and receive downloadable highlight reels.

## Key Decisions

- **Platform**: iOS app (React Native)
- **Processing**: Cloud backend (Python FastAPI + Celery workers)
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
Upload on S3 → Download to worker → Stage 1: Setup (0-10%)
→ Stage 2: Detection & Tracking per-frame (10-60%)
→ Stage 3: Event Detection (60-75%)
→ Stage 4: Clip Extraction via ffmpeg (75-90%)
→ Stage 5: Compile game + player reels (90-98%)
→ Stage 6: Upload reels to S3, mark done (98-100%)
```

Two Celery tasks split by the player selection step:
1. `process_video_detection` — Downloads video, runs YOLO detection/tracking, extracts preview
2. `process_video_highlights` — Detects events, extracts clips, compiles reels, uploads to S3

## Phased Implementation

### Phase 1: Backend Core (Complete)

- Project scaffolding (Docker, FastAPI, requirements)
- DB models + Alembic migrations
- JWT auth system (signup/login/me)
- S3 presigned URL upload flow
- Pipeline modules refactored from possession_tracker.py
- MVP event detection (possession changes, potential scores, fast breaks)
- ffmpeg clip extraction + concatenation
- Pipeline orchestrator
- Celery integration with progress updates
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

- Hoop/court detection for real scoring detection
- Team color clustering (K-means on jersey HSV histograms)
- Shot detection (ball trajectory toward hoop)
- Advanced events: steals, blocks, assists, rebounds, crossovers
- Highlight quality ranking + configurable reel length
- Enable BotSORT Re-ID for better player identity persistence

## Data Flow

```
Phone → POST /videos/upload-url → presigned URL
Phone → PUT to S3 (direct upload)
Phone → POST /videos/confirm → triggers preview extraction
Phone → POST /jobs → queues Celery task
Phone → GET /jobs/{id}/progress (poll 3s) → progress updates
Worker → runs full pipeline → uploads reels to S3
Phone → GET /highlights → presigned download URLs
Phone → stream/download highlight reels
```
