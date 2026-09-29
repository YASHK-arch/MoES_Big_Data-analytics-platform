"""Add composite indexes for dashboard summary and analytics queries.

Revision ID: 0010_dashboard_perf_indexes
Revises: 0009_expanded_categories
Create Date: 2026-09-30 04:50:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_dashboard_perf_indexes"
down_revision = "0009_expanded_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Composite index for category filtering and ordering
    op.create_index(
        "idx_weather_reports_cat_occ",
        "weather_reports",
        ["reported_category", "occurred_at"],
        unique=False,
    )

    # 2. Composite index for severity filtering and ordering
    op.create_index(
        "idx_weather_reports_sev_occ",
        "weather_reports",
        ["severity", "occurred_at"],
        unique=False,
    )

    # 3. Composite covering index for dashboard summary aggregations
    op.create_index(
        "idx_weather_reports_dashboard_summary",
        "weather_reports",
        ["occurred_at", "verification_status", "severity", "reported_category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_weather_reports_dashboard_summary", table_name="weather_reports")
    op.drop_index("idx_weather_reports_sev_occ", table_name="weather_reports")
    op.drop_index("idx_weather_reports_cat_occ", table_name="weather_reports")
