"""Add is_test_fixture column to evidence_items.

Revision ID: 0016_add_evidence_is_test_fixture
Revises: 0015_geo_sort_index
Create Date: 2026-09-30 16:26:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_add_evidence_is_test_fixture"
down_revision = "0015_geo_sort_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column("is_test_fixture", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_evidence_items_is_test_fixture",
        "evidence_items",
        ["is_test_fixture"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_items_is_test_fixture", table_name="evidence_items")
    op.drop_column("evidence_items", "is_test_fixture")
