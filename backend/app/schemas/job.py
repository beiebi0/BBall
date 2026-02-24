from pydantic import BaseModel


class CreateJobRequest(BaseModel):
    video_id: str


class SelectPlayerRequest(BaseModel):
    player_track_id: int
    team_color_hex: str | None = None


class JobResponse(BaseModel):
    id: str
    video_id: str
    status: str
    progress: int
    stage: str | None
    error_message: str | None
    selected_player_track_id: int | None
    team_color_hex: str | None
    created_at: str

    model_config = {"from_attributes": True}


class JobProgressResponse(BaseModel):
    status: str
    progress: int
    stage: str | None


class JobPreviewResponse(BaseModel):
    preview_url: str
    players: list[dict]
