from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://bball:bball@localhost:5432/bball"
    database_url_sync: str = "postgresql://bball:bball@localhost:5432/bball"

    # GCS
    gcs_bucket: str = "bball-videos"
    gcs_project_id: str = ""
    gcs_service_account_json: str = ""
    gcs_endpoint_url: str = ""

    # Pub/Sub
    pubsub_project_id: str = ""
    pubsub_emulator_host: str = ""
    pubsub_topic_detection: str = "video-detection"
    pubsub_topic_highlights: str = "video-highlights"
    pubsub_subscription_detection: str = "video-detection-sub"
    pubsub_subscription_highlights: str = "video-highlights-sub"

    # CORS
    cors_origins: str = "*"

    # Auth
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 168  # 7 days

    # ML Models
    player_model_path: str = "yolo11m.pt"
    ball_model_path: str = "yolo11m.pt"
    pose_model_path: str = "yolo11n-pose.pt"
    tracker_config_path: str = "models/botsort.yaml"

    # Pipeline
    clip_padding_before: float = 3.0
    clip_padding_after: float = 2.0
    possession_smoothing_window: int = 10
    ball_conf_threshold: float = 0.10
    player_conf_threshold: float = 0.25

    # Rim Detection (Roboflow)
    roboflow_api_key: str = ""
    rim_model_id: str = "basketball-xil7x/1"
    rim_conf_threshold: float = 0.30
    rim_num_samples: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
