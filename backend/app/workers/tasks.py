import json
import logging
import os
import tempfile
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.storage import download_file, upload_file

logger = logging.getLogger(__name__)

# Sync engine for worker tasks (can't use async in sync workers)
_engine = create_engine(settings.database_url_sync)
SyncSession = sessionmaker(bind=_engine)


class JobCancelledError(Exception):
    pass


def _update_job(session: Session, job_id: str, **kwargs):
    from app.models.job import Job

    job = session.query(Job).filter(Job.id == job_id).first()
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        session.commit()


def _check_cancelled(session: Session, job_id: str):
    """Check if a job has been cancelled. Raises JobCancelledError if so."""
    from app.models.job import Job

    session.expire_all()  # force fresh read from DB
    job = session.query(Job).filter(Job.id == job_id).first()
    if job and job.status == "cancelled":
        raise JobCancelledError(f"Job {job_id} was cancelled")


def process_video_detection(job_id: str):
    """
    Phase 1: Download video from GCS, run YOLO detection/tracking.
    Sets job status to 'awaiting_selection' when done.
    """
    from app.models.job import Job
    from app.models.video import Video

    session = SyncSession()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("Job %s not found", job_id)
            return

        video = session.query(Video).filter(Video.id == job.video_id).first()
        if not video:
            _update_job(session, job_id, status="failed", error_message="Video not found")
            return

        _update_job(session, job_id, status="processing", progress=5, stage="downloading")

        # Download video from GCS
        work_dir = tempfile.mkdtemp(prefix=f"bball_{job_id}_")
        local_video = os.path.join(work_dir, "source.mp4")
        download_file(video.gcs_key, local_video)

        _update_job(session, job_id, progress=10, stage="detecting")

        # Run pipeline detection phase
        from pipeline.orchestrator import PipelineOrchestrator

        def progress_cb(pct: int, msg: str):
            _check_cancelled(session, job_id)
            _update_job(session, job_id, progress=pct, stage=msg)

        orchestrator = PipelineOrchestrator(
            player_model_path=settings.player_model_path,
            ball_model_path=settings.ball_model_path,
            pose_model_path=settings.pose_model_path,
            tracker_config_path=settings.tracker_config_path,
            player_conf=settings.player_conf_threshold,
            ball_conf=settings.ball_conf_threshold,
            smoothing_window=settings.possession_smoothing_window,
            roboflow_api_key=settings.roboflow_api_key,
            rim_model_id=settings.rim_model_id,
            rim_conf=settings.rim_conf_threshold,
            rim_num_samples=settings.rim_num_samples,
            frame_skip=settings.frame_skip,
            progress_callback=progress_cb,
        )

        # Get video info and update video record
        info = orchestrator.get_video_info(local_video)
        video.duration_secs = info["duration"]
        video.resolution = f"{info['width']}x{info['height']}"
        session.commit()

        # Run detection
        all_frames = orchestrator.run_detection(local_video)

        # Cache detection results to GCS so Phase 2 can skip re-detection
        from pipeline.models import serialize_detection_cache
        cache_json = serialize_detection_cache(all_frames, orchestrator._rim_position)
        cache_path = os.path.join(work_dir, "detection_cache.json")
        with open(cache_path, "w") as f:
            f.write(cache_json)
        upload_file(cache_path, f"detection_cache/{job_id}/frames.json")
        logger.info("Detection cache uploaded for job %s (%d frames)", job_id, len(all_frames))

        # Pick the middle frame for annotated preview
        mid = all_frames[len(all_frames) // 2] if all_frames else None

        # Extract annotated preview frame and upload to GCS
        preview_bytes = None
        if mid:
            preview_bytes = orchestrator.extract_annotated_preview(local_video, mid)
        if not preview_bytes:
            preview_bytes = orchestrator.extract_preview_frame(local_video)
        if preview_bytes:
            preview_key = f"previews/{job_id}/preview.jpg"
            preview_path = os.path.join(work_dir, "preview.jpg")
            with open(preview_path, "wb") as f:
                f.write(preview_bytes)
            upload_file(preview_path, preview_key)

        # Collect unique player track IDs and upload players.json
        if mid and mid.players:
            players_list = []
            seen_ids = set()
            for p in mid.players:
                if p.track_id not in seen_ids:
                    seen_ids.add(p.track_id)
                    players_list.append({
                        "track_id": p.track_id,
                        "bbox": [p.bbox.x1, p.bbox.y1, p.bbox.x2, p.bbox.y2],
                    })
            players_path = os.path.join(work_dir, "players.json")
            with open(players_path, "w") as f:
                json.dump(players_list, f)
            upload_file(players_path, f"previews/{job_id}/players.json")

        _update_job(
            session, job_id,
            status="awaiting_selection",
            progress=60,
            stage="Awaiting player selection",
        )

        logger.info("Detection phase complete for job %s", job_id)

    except JobCancelledError:
        logger.info("Detection cancelled for job %s", job_id)
    except Exception as e:
        logger.exception("Detection failed for job %s", job_id)
        _update_job(
            session, job_id,
            status="failed",
            error_message=str(e),
        )
    finally:
        session.close()


def process_video_highlights(job_id: str):
    """
    Phase 2: After player selection, detect events, extract clips,
    compile highlight reels, upload to GCS.
    """
    from app.models.highlight import Highlight
    from app.models.job import Job
    from app.models.video import Video

    session = SyncSession()
    try:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("Job %s not found", job_id)
            return

        video = session.query(Video).filter(Video.id == job.video_id).first()
        if not video:
            _update_job(session, job_id, status="failed", error_message="Video not found")
            return

        _update_job(session, job_id, status="processing", progress=62, stage="generating highlights")

        # Download video
        work_dir = tempfile.mkdtemp(prefix=f"bball_{job_id}_hl_")
        local_video = os.path.join(work_dir, "source.mp4")
        download_file(video.gcs_key, local_video)
        output_dir = os.path.join(work_dir, "output")

        def progress_cb(pct: int, msg: str):
            _check_cancelled(session, job_id)
            _update_job(session, job_id, progress=pct, stage=msg)

        from pipeline.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(
            player_model_path=settings.player_model_path,
            ball_model_path=settings.ball_model_path,
            pose_model_path=settings.pose_model_path,
            tracker_config_path=settings.tracker_config_path,
            player_conf=settings.player_conf_threshold,
            ball_conf=settings.ball_conf_threshold,
            clip_padding_before=settings.clip_padding_before,
            clip_padding_after=settings.clip_padding_after,
            roboflow_api_key=settings.roboflow_api_key,
            rim_model_id=settings.rim_model_id,
            rim_conf=settings.rim_conf_threshold,
            rim_num_samples=settings.rim_num_samples,
            frame_skip=settings.frame_skip,
            progress_callback=progress_cb,
        )

        # Try to load cached detection results from Phase 1
        from app.core.storage import download_blob_bytes
        from pipeline.models import deserialize_detection_cache

        cache_data = download_blob_bytes(f"detection_cache/{job_id}/frames.json")
        if cache_data:
            logger.info("Loaded detection cache for job %s, skipping re-detection", job_id)
            cached_frames, rim_position = deserialize_detection_cache(cache_data.decode("utf-8"))
            result = orchestrator.run_highlights_from_cache(
                video_path=local_video,
                output_dir=output_dir,
                cached_frames=cached_frames,
                rim_position=rim_position,
                selected_player_id=job.selected_player_track_id,
            )
        else:
            logger.warning("No detection cache for job %s, running full pipeline", job_id)
            result = orchestrator.run_full_pipeline(
                video_path=local_video,
                output_dir=output_dir,
                selected_player_id=job.selected_player_track_id,
            )

        # Upload reels to GCS and create highlight records
        for reel_type, reel_path in result["reel_paths"].items():
            gcs_key = f"highlights/{job_id}/{reel_type}.mp4"
            upload_file(reel_path, gcs_key)

            file_size = os.path.getsize(reel_path)
            hl_type = "game" if reel_type == "game_reel" else "player"

            highlight = Highlight(
                job_id=uuid.UUID(job_id),
                highlight_type=hl_type,
                player_track_id=job.selected_player_track_id if hl_type == "player" else None,
                gcs_key=gcs_key,
                file_size_bytes=file_size,
            )
            session.add(highlight)

        video.status = "done"
        session.commit()

        _update_job(
            session, job_id,
            status="completed",
            progress=100,
            stage="Done",
        )

        logger.info("Highlight generation complete for job %s", job_id)

        # Cleanup
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)

    except JobCancelledError:
        logger.info("Highlight generation cancelled for job %s", job_id)
    except Exception as e:
        logger.exception("Highlight generation failed for job %s", job_id)
        _update_job(
            session, job_id,
            status="failed",
            error_message=str(e),
        )
    finally:
        session.close()
