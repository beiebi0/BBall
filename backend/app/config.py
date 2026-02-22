from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://bball:bball@localhost:5432/bball"
    database_url_sync: str = "postgresql://bball:bball@localhost:5432/bball"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    s3_bucket: str = "bball-videos"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = "http://localhost:9000"

    # Auth
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 168  # 7 days

    # ML Models
    player_model_path: str = "models/yolov8n.pt"
    ball_model_path: str = "models/ball_detector_model.pt"
    tracker_config_path: str = "models/botsort.yaml"

    # Pipeline
    clip_padding_before: float = 3.0
    clip_padding_after: float = 2.0
    possession_smoothing_window: int = 10
    ball_conf_threshold: float = 0.10
    player_conf_threshold: float = 0.25

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
