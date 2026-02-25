from pydantic import BaseModel


class UploadURLRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"


class UploadURLResponse(BaseModel):
    video_id: str
    upload_url: str
    gcs_key: str


class VideoResponse(BaseModel):
    id: str
    filename: str | None
    status: str
    duration_secs: float | None
    resolution: str | None
    created_at: str

    model_config = {"from_attributes": True}
