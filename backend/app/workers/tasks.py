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


def _update_job(session: Session, job_id: str, **kwargs):
    from app.models.job import Job

    job = session.query(Job).filter(Job.id == job_id).first()
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        session.commit()


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
        download_file(video.s3_key, local_video)

        _update_job(session, job_id, progress=10, stage="detecting")

        # Run pipeline detection phase
        from pipeline.orchestrator import PipelineOrchestrator

        def progress_cb(pct: int, msg: str):
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
            progress_callback=progress_cb,
        )

        # Get video info and update video record
        info = orchestrator.get_video_info(local_video)
        video.duration_secs = info["duration"]
        video.resolution = f"{info['width']}x{info['height']}"
        session.commit()

        # Run detection
        orchestrator.run_detection(local_video)

        # Extract preview frame and upload to GCS
        preview_bytes = orchestrator.extract_preview_frame(local_video)
        if preview_bytes:
            preview_key = f"previews/{job_id}/preview.jpg"
            preview_path = os.path.join(work_dir, "preview.jpg")
            with open(preview_path, "wb") as f:
                f.write(preview_bytes)
            upload_file(preview_path, preview_key)

        _update_job(
            session, job_id,
            status="awaiting_selection",
            progress=60,
            stage="Awaiting player selection",
        )

        logger.info("Detection phase complete for job %s", job_id)

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
        download_file(video.s3_key, local_video)
        output_dir = os.path.join(work_dir, "output")

        def progress_cb(pct: int, msg: str):
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
            progress_callback=progress_cb,
        )

        result = orchestrator.run_full_pipeline(
            video_path=local_video,
            output_dir=output_dir,
            selected_player_id=job.selected_player_track_id,
        )

        # Upload reels to GCS and create highlight records
        for reel_type, reel_path in result["reel_paths"].items():
            s3_key = f"highlights/{job_id}/{reel_type}.mp4"
            upload_file(reel_path, s3_key)

            file_size = os.path.getsize(reel_path)
            hl_type = "game" if reel_type == "game_reel" else "player"

            highlight = Highlight(
                job_id=uuid.UUID(job_id),
                highlight_type=hl_type,
                player_track_id=job.selected_player_track_id if hl_type == "player" else None,
                s3_key=s3_key,
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

    except Exception as e:
        logger.exception("Highlight generation failed for job %s", job_id)
        _update_job(
            session, job_id,
            status="failed",
            error_message=str(e),
        )
    finally:
        session.close()
