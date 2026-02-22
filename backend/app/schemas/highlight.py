from pydantic import BaseModel


class HighlightResponse(BaseModel):
    id: str
    job_id: str
    highlight_type: str
    player_track_id: int | None
    duration_secs: float | None
    file_size_bytes: int | None
    download_url: str | None = None
    created_at: str

    model_config = {"from_attributes": True}
