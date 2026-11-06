"""product shop name and type

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("shop_name", sa.Text))
    op.add_column("products", sa.Column("shop_type", sa.String(20)))


def downgrade() -> None:
    op.drop_column("products", "shop_type")
    op.drop_column("products", "shop_name")
