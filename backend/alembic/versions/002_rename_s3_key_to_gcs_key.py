"""Rename s3_key to gcs_key

Revision ID: 002
Revises: 001
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("videos", "s3_key", new_column_name="gcs_key")
    op.alter_column("highlights", "s3_key", new_column_name="gcs_key")


def downgrade() -> None:
    op.alter_column("videos", "gcs_key", new_column_name="s3_key")
    op.alter_column("highlights", "gcs_key", new_column_name="s3_key")
