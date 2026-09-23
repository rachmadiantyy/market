"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    product_status = sa.Enum(
        "draft", "active", "archived", name="product_status"
    )
    content_type = sa.Enum("text", "image", name="content_type")
    content_status = sa.Enum(
        "draft",
        "queued",
        "generating",
        "ready",
        "scheduled",
        "published",
        "failed",
        name="content_status",
    )
    job_status = sa.Enum(
        "pending", "running", "succeeded", "failed", name="job_status"
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("affiliate_url", sa.String(1024)),
        sa.Column("image_url", sa.String(1024)),
        sa.Column("price", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(8), nullable=False, server_default="IDR"),
        sa.Column("status", product_status, nullable=False, server_default="draft"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
        ),
        sa.Column("content_type", content_type, nullable=False, server_default="text"),
        sa.Column("status", content_status, nullable=False, server_default="draft"),
        sa.Column("title", sa.String(255)),
        sa.Column("body", sa.Text()),
        sa.Column("media_url", sa.String(1024)),
        sa.Column("prompt", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("queue", sa.String(64), nullable=False, server_default="default"),
        sa.Column("task", sa.String(128), nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB(), server_default="{}"),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
        ),
        sa.Column("channel", sa.String(64)),
        sa.Column("value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_products_status", "products", ["status"])
    op.create_index("ix_content_items_status", "content_items", ["status"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_analytics_events_event_type", table_name="analytics_events")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_content_items_status", table_name="content_items")
    op.drop_index("ix_products_status", table_name="products")
    op.drop_table("analytics_events")
    op.drop_table("jobs")
    op.drop_table("content_items")
    op.drop_table("products")
    for enum in ("job_status", "content_status", "content_type", "product_status"):
        sa.Enum(name=enum).drop(op.get_bind(), checkfirst=True)
