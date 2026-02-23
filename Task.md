# Tasks

## Completed

- [x] Prototype possession tracker (YOLOv8 + BotSORT)
- [x] Upgrade detection to YOLO11m + pose-based ball filtering
- [x] Project scaffolding (Docker Compose, FastAPI, Dockerfile, requirements.txt)
- [x] Database models + Alembic migration (users, videos, jobs, events, highlights)
- [x] JWT authentication (signup, login, get current user)
- [x] S3 presigned URL upload flow (upload-url, confirm, list videos)
- [x] Player detection module (YOLO11m + BotSORT)
- [x] Ball detection module (YOLO11m COCO class 32 + YOLO11n-pose filtering)
- [x] Possession tracking with temporal smoothing (6/10 majority)
- [x] MVP event detection (possession changes, potential scores, fast breaks)
- [x] ffmpeg clip extraction + reel concatenation
- [x] Pipeline orchestrator with progress stages (0-100%)
- [x] Celery tasks (process_video_detection, process_video_highlights)
- [x] Jobs API (create, status, progress polling, player selection)
- [x] Highlights API (list, get, download)
- [x] Project docs (README, Master_Plan, User_journey, Implementation_plan, Task, Rules)
- [x] Integrate YOLO11m + Zero-Face filtering into pipeline code (player_detector, ball_detector)
- [x] Add unit tests for detection modules (test_ball_detector, test_player_detector)
- [x] Remove obsolete prototype (`possession_tracker.py`) and redundant root `botsort.yaml`
- [x] Integrate Roboflow rim detection (`RimDetector`, orchestrator wiring, rim-proximity scoring in `EventDetector`, config settings, task plumbing)
- [x] Add unit tests for RimDetector (test_rim_detector.py — 15 tests)

## Next Steps

### Test the Backend (Priority)

The entire Phase 1 backend has been built but **never run or tested**. Before moving to the iOS app, verify everything actually works end-to-end.

- [ ] Spin up Docker Compose stack (Postgres, Redis, MinIO, API, Worker)
- [ ] Run Alembic migration against live database
- [ ] Test auth flow: signup → login → token works on protected routes
- [ ] Test upload flow: get presigned URL → upload a video to MinIO → confirm
- [ ] Test job creation: create job → verify Celery task gets queued
- [ ] Test detection pipeline: run worker on a real basketball video, check progress updates
- [ ] Test player selection: submit player track ID, verify highlight generation kicks off
- [ ] Test highlights: verify reels are uploaded to S3 and download URLs work
- [ ] Fix any bugs found during testing

### Phase 2: iOS App

- [ ] React Native + TypeScript project setup
- [ ] Auth screens (signup / login)
- [ ] Home screen (upload button + video history)
- [ ] Video upload (camera roll picker → presigned URL → S3 → confirm)
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
