"""Add covering index for dashboard summary aggregations.

Revision ID: 0011_summary_covering_index
Revises: 0010_dashboard_perf_indexes
Create Date: 2026-09-30 05:54:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_summary_covering_index"
down_revision = "0010_dashboard_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_weather_reports_summary_cov",
        "weather_reports",
        ["verification_status", "severity"],
        postgresql_include=["credibility_score", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_weather_reports_summary_cov", table_name="weather_reports")
