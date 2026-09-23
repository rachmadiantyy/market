"""product media and telegram fields

Revision ID: 0003_product_media
Revises: 0002_ai_generations
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_product_media"
down_revision: Union[str, None] = "0002_ai_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("commission", sa.Numeric(12, 2)))
    op.add_column("products", sa.Column("category", sa.String(128)))
    op.add_column("products", sa.Column("target_audience", sa.Text()))

    media_type = sa.Enum("image", "video", name="media_type")

    op.create_table(
        "product_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(32), nullable=False, server_default="telegram"),
        sa.Column("telegram_file_id", sa.String(255)),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_product_media_product_id", "product_media", ["product_id"])
    op.create_index("ix_product_media_media_type", "product_media", ["media_type"])


def downgrade() -> None:
    op.drop_index("ix_product_media_media_type", table_name="product_media")
    op.drop_index("ix_product_media_product_id", table_name="product_media")
    op.drop_table("product_media")
    sa.Enum(name="media_type").drop(op.get_bind(), checkfirst=True)

    op.drop_column("products", "target_audience")
    op.drop_column("products", "category")
    op.drop_column("products", "commission")
