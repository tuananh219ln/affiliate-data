"""initial tables

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "platform_sessions",
        sa.Column("platform", sa.String(20), primary_key=True),
        sa.Column("storage_state", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text),
        *_timestamps(),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("shop_id", sa.String(64)),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("price", sa.Numeric(14, 2)),
        sa.Column("original_price", sa.Numeric(14, 2)),
        sa.Column("image_url", sa.Text),
        sa.Column("url", sa.Text),
        sa.Column("sold", sa.BigInteger),
        sa.Column("rating", sa.Float),
        sa.Column("commission_rate", sa.Float),
        sa.Column("commission_amount", sa.Numeric(14, 2)),
        sa.Column("affiliate_link", sa.Text),
        sa.Column("keyword", sa.Text),
        sa.Column("raw", JSONB),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("platform", "external_id"),
    )
    op.create_table(
        "trending_videos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("author", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("cover_url", sa.Text),
        sa.Column("url", sa.Text),
        sa.Column("views", sa.BigInteger),
        sa.Column("likes", sa.BigInteger),
        sa.Column("comments", sa.BigInteger),
        sa.Column("shares", sa.BigInteger),
        sa.Column("keyword", sa.Text),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("raw", JSONB),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("platform", "external_id"),
    )
    op.create_table(
        "conversions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("item_name", sa.Text),
        sa.Column("order_amount", sa.Numeric(14, 2)),
        sa.Column("commission", sa.Numeric(14, 2)),
        sa.Column("status", sa.String(40)),
        sa.Column("ordered_at", sa.DateTime(timezone=True)),
        sa.Column("raw", JSONB),
        *_timestamps(),
        sa.UniqueConstraint("platform", "order_id", "item_id"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("result", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table(
        "watches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("every_hours", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    for table in ("watches", "jobs", "conversions", "trending_videos", "products", "platform_sessions"):
        op.drop_table(table)
