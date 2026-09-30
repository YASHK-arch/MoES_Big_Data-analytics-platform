"""Drop exact duplicate indexes on weather_reports table.

Drops:
- ix_weather_reports_tracking_id (duplicates unique btree weather_reports_tracking_id_key)
- ix_weather_reports_credibility_score (duplicates idx_weather_reports_credibility)

Revision ID: 0013_drop_duplicate_report_indexes
Revises: 0012_report_list_index
Create Date: 2026-09-30 10:40:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_drop_duplicate_indexes"
down_revision = "0012_report_list_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop ix_weather_reports_tracking_id (exact duplicate of weather_reports_tracking_id_key)
    op.drop_index("ix_weather_reports_tracking_id", table_name="weather_reports")

    # 2. Drop ix_weather_reports_credibility_score (exact duplicate of idx_weather_reports_credibility)
    op.drop_index("ix_weather_reports_credibility_score", table_name="weather_reports")


def downgrade() -> None:
    # Recreate the dropped indexes with identical schema
    op.create_index(
        "ix_weather_reports_tracking_id",
        "weather_reports",
        ["tracking_id"],
        unique=True,
    )
    op.create_index(
        "ix_weather_reports_credibility_score",
        "weather_reports",
        ["credibility_score"],
        unique=False,
    )
