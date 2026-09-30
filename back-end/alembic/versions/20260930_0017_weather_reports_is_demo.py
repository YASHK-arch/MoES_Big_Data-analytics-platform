"""Add is_demo column to weather_reports with backfill and index.

Revision ID: 0017_report_is_demo
Revises: 0016_evidence_test_fixture
Create Date: 2026-09-30 16:55:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_report_is_demo"
down_revision = "0016_evidence_test_fixture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    res = conn.execute(
        sa.text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'weather_reports' AND column_name = 'is_demo';"
        )
    ).scalar()
    if not res:
        op.add_column(
            "weather_reports",
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.create_index(
            "ix_weather_reports_is_demo",
            "weather_reports",
            ["is_demo"],
            unique=False,
        )

    # Backfill is_demo from [DEMO] title prefix and DEMO- tracking IDs
    conn.execute(
        sa.text(
            "UPDATE weather_reports "
            "SET is_demo = true "
            "WHERE title LIKE '[DEMO]%' OR tracking_id LIKE 'DEMO-%';"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    res = conn.execute(
        sa.text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'weather_reports' AND column_name = 'is_demo';"
        )
    ).scalar()
    if res:
        op.drop_index("ix_weather_reports_is_demo", table_name="weather_reports")
        op.drop_column("weather_reports", "is_demo")
