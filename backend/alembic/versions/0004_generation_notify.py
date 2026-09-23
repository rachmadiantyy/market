"""telegram notification target for ai generations

Revision ID: 0004_generation_notify
Revises: 0003_product_media
Create Date: 2026-09-23

Adds the chat id a generation should report back to. Generations started from
the Telegram bot set this so the worker can push the finished result to that
chat; HTTP-started generations leave it NULL and are only visible in the
dashboard.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_generation_notify"
down_revision: Union[str, None] = "0003_product_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_generations", sa.Column("notify_chat_id", sa.String(64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ai_generations", "notify_chat_id")
