"""Add composite index on (occurred_at DESC, created_at DESC) for fast incident listing.

Revision ID: 0012_report_list_index
Revises: 0011_summary_covering_index
Create Date: 2026-09-30 06:40:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0012_report_list_index"
down_revision = "0011_summary_covering_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_weather_reports_occ_created",
        "weather_reports",
        [sa.text("occurred_at DESC"), sa.text("created_at DESC")],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_weather_reports_occ_created", table_name="weather_reports")
