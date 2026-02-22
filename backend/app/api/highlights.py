from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.s3 import generate_presigned_download_url
from app.core.security import get_current_user
from app.models.highlight import Highlight
from app.models.job import Job
from app.models.user import User
from app.schemas.highlight import HighlightResponse

router = APIRouter()


@router.get("", response_model=list[HighlightResponse])
async def list_highlights(
    job_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify job belongs to user
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(Highlight).where(Highlight.job_id == job_id)
    )
    highlights = result.scalars().all()

    return [
        HighlightResponse(
            id=str(h.id),
            job_id=str(h.job_id),
            highlight_type=h.highlight_type,
            player_track_id=h.player_track_id,
            duration_secs=h.duration_secs,
            file_size_bytes=h.file_size_bytes,
            download_url=generate_presigned_download_url(h.s3_key),
            created_at=str(h.created_at),
        )
        for h in highlights
    ]


@router.get("/{highlight_id}", response_model=HighlightResponse)
async def get_highlight(
    highlight_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Highlight, Job)
        .join(Job, Highlight.job_id == Job.id)
        .where(Highlight.id == highlight_id, Job.user_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Highlight not found")

    h = row[0]
    return HighlightResponse(
        id=str(h.id),
        job_id=str(h.job_id),
        highlight_type=h.highlight_type,
        player_track_id=h.player_track_id,
        duration_secs=h.duration_secs,
        file_size_bytes=h.file_size_bytes,
        download_url=generate_presigned_download_url(h.s3_key),
        created_at=str(h.created_at),
    )


@router.get("/{highlight_id}/download")
async def download_highlight(
    highlight_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Highlight, Job)
        .join(Job, Highlight.job_id == Job.id)
        .where(Highlight.id == highlight_id, Job.user_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Highlight not found")

    h = row[0]
    url = generate_presigned_download_url(h.s3_key, expires_in=7200)
    return {"download_url": url}
