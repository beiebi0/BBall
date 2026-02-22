"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(255)),
        sa.Column("duration_secs", sa.Float),
        sa.Column("resolution", sa.String(20)),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploading"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_videos_user", "videos", ["user_id"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("selected_player_track_id", sa.Integer),
        sa.Column("team_color_hex", sa.String(10)),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("stage", sa.String(50)),
        sa.Column("error_message", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_jobs_user", "jobs", ["user_id"])
    op.create_index("idx_jobs_video", "jobs", ["video_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("frame_start", sa.Integer, nullable=False),
        sa.Column("frame_end", sa.Integer, nullable=False),
        sa.Column("time_start", sa.Float, nullable=False),
        sa.Column("time_end", sa.Float, nullable=False),
        sa.Column("player_track_id", sa.Integer),
        sa.Column("confidence", sa.Float),
        sa.Column("metadata_json", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_events_job", "events", ["job_id"])

    op.create_table(
        "highlights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("highlight_type", sa.String(20), nullable=False),
        sa.Column("player_track_id", sa.Integer),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("duration_secs", sa.Float),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_highlights_job", "highlights", ["job_id"])


def downgrade() -> None:
    op.drop_table("highlights")
    op.drop_table("events")
    op.drop_table("jobs")
    op.drop_table("videos")
    op.drop_table("users")
