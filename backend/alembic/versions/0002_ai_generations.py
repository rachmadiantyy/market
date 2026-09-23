"""ai generations

Revision ID: 0002_ai_generations
Revises: 0001_initial
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_ai_generations"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    generation_status = sa.Enum(
        "queued", "processing", "completed", "failed", name="generation_status"
    )
    ai_content_type = sa.Enum(
        "caption",
        "hook",
        "short_video_script",
        "product_description",
        "cta",
        name="ai_content_type",
    )
    ai_platform = sa.Enum(
        "tiktok", "instagram", "facebook", "threads", "x", name="ai_platform"
    )

    op.create_table(
        "ai_generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
        ),
        sa.Column("type", ai_content_type, nullable=False, server_default="caption"),
        sa.Column("platform", ai_platform, nullable=False, server_default="tiktok"),
        sa.Column("variations", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", generation_status, nullable=False, server_default="queued"),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("model", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.create_index("ix_ai_generations_status", "ai_generations", ["status"])
    op.create_index("ix_ai_generations_created_at", "ai_generations", ["created_at"])
    op.create_index("ix_ai_generations_product_id", "ai_generations", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_generations_product_id", table_name="ai_generations")
    op.drop_index("ix_ai_generations_created_at", table_name="ai_generations")
    op.drop_index("ix_ai_generations_status", table_name="ai_generations")
    op.drop_table("ai_generations")
    for enum in ("ai_platform", "ai_content_type", "generation_status"):
        sa.Enum(name=enum).drop(op.get_bind(), checkfirst=True)
