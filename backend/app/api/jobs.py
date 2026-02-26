import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.storage import download_blob_bytes, generate_signed_download_url
from app.models.highlight import Highlight
from app.models.job import Job
from app.models.user import User
from app.models.video import Video
from app.schemas.job import (
    CreateJobRequest,
    JobPreviewResponse,
    JobProgressResponse,
    JobResponse,
    SelectPlayerRequest,
)

router = APIRouter()


@router.post("", response_model=JobResponse)
async def create_job(
    req: CreateJobRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Video).where(
            Video.id == req.video_id, Video.user_id == current_user.id
        )
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != "uploaded":
        raise HTTPException(status_code=400, detail="Video not ready for processing")

    job = Job(
        video_id=video.id,
        user_id=current_user.id,
        status="queued",
        progress=0,
    )
    db.add(job)
    video.status = "processing"
    await db.commit()
    await db.refresh(job)

    # Publish to Pub/Sub
    from app.core.pubsub import publish_detection_task

    publish_detection_task(str(job.id))

    return _job_response(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_user_job(db, job_id, current_user.id)
    return _job_response(job)


@router.get("/{job_id}/progress", response_model=JobProgressResponse)
async def get_job_progress(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_user_job(db, job_id, current_user.id)
    return JobProgressResponse(
        status=job.status,
        progress=job.progress,
        stage=job.stage,
    )


@router.get("/{job_id}/preview", response_model=JobPreviewResponse)
async def get_job_preview(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_user_job(db, job_id, current_user.id)

    if job.status not in ("awaiting_selection", "processing", "completed"):
        raise HTTPException(
            status_code=400, detail="Preview not available for this job status"
        )

    preview_key = f"previews/{job_id}/preview.jpg"
    preview_url = await asyncio.to_thread(generate_signed_download_url, preview_key)

    players_key = f"previews/{job_id}/players.json"
    players_bytes = await asyncio.to_thread(download_blob_bytes, players_key)
    players = json.loads(players_bytes) if players_bytes else []

    return JobPreviewResponse(preview_url=preview_url, players=players)


@router.post("/{job_id}/select-player", response_model=JobResponse)
async def select_player(
    job_id: str,
    req: SelectPlayerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_user_job(db, job_id, current_user.id)

    if job.status != "awaiting_selection":
        raise HTTPException(
            status_code=400, detail="Job is not awaiting player selection"
        )

    job.selected_player_track_id = req.player_track_id
    job.team_color_hex = req.team_color_hex
    job.status = "processing"
    job.stage = "Starting highlight generation"
    await db.commit()
    await db.refresh(job)

    # Publish to Pub/Sub
    from app.core.pubsub import publish_highlights_task

    publish_highlights_task(str(job.id))

    return _job_response(job)


@router.post("/{job_id}/reselect", response_model=JobResponse)
async def reselect_player(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_user_job(db, job_id, current_user.id)

    if job.status != "completed":
        raise HTTPException(
            status_code=400, detail="Can only re-select player on a completed job"
        )

    # Delete existing highlights for this job
    await db.execute(
        sa_delete(Highlight).where(Highlight.job_id == job.id)
    )

    # Reset job to awaiting_selection state
    job.status = "awaiting_selection"
    job.progress = 60
    job.stage = "Awaiting player selection"
    job.selected_player_track_id = None
    job.team_color_hex = None
    await db.commit()
    await db.refresh(job)

    return _job_response(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_user_job(db, job_id, current_user.id)

    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=400, detail=f"Job is already {job.status}"
        )

    job.status = "cancelled"
    job.stage = "Cancelled by user"
    await db.commit()
    await db.refresh(job)

    return _job_response(job)


async def _get_user_job(db: AsyncSession, job_id: str, user_id: uuid.UUID) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=str(job.id),
        video_id=str(job.video_id),
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        error_message=job.error_message,
        selected_player_track_id=job.selected_player_track_id,
        team_color_hex=job.team_color_hex,
        created_at=str(job.created_at),
    )
