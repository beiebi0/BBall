import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.s3 import generate_presigned_upload_url
from app.core.security import get_current_user
from app.models.user import User
from app.models.video import Video
from app.schemas.video import UploadURLRequest, UploadURLResponse, VideoResponse

router = APIRouter()


@router.post("/upload-url", response_model=UploadURLResponse)
async def get_upload_url(
    req: UploadURLRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    video_id = uuid.uuid4()
    s3_key = f"uploads/{current_user.id}/{video_id}/{req.filename}"

    video = Video(
        id=video_id,
        user_id=current_user.id,
        s3_key=s3_key,
        filename=req.filename,
        status="uploading",
    )
    db.add(video)
    await db.commit()

    upload_url = generate_presigned_upload_url(s3_key, req.content_type)

    return UploadURLResponse(
        video_id=str(video_id),
        upload_url=upload_url,
        s3_key=s3_key,
    )


@router.post("/{video_id}/confirm", response_model=VideoResponse)
async def confirm_upload(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    video.status = "uploaded"
    await db.commit()
    await db.refresh(video)

    return VideoResponse(
        id=str(video.id),
        filename=video.filename,
        status=video.status,
        duration_secs=video.duration_secs,
        resolution=video.resolution,
        created_at=str(video.created_at),
    )


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Video)
        .where(Video.user_id == current_user.id)
        .order_by(Video.created_at.desc())
    )
    videos = result.scalars().all()
    return [
        VideoResponse(
            id=str(v.id),
            filename=v.filename,
            status=v.status,
            duration_secs=v.duration_secs,
            resolution=v.resolution,
            created_at=str(v.created_at),
        )
        for v in videos
    ]
