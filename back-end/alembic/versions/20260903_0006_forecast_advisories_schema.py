"""Forecast Advisories Schema for Official IMD & NDMA Advisories & Cyclone Tracks

Revision ID: 0006_forecast_advisories
Revises: 0005_weather_reports_archive
Create Date: 2026-09-03 02:45:00.000000+00:00

Additive migration creating the forecast_advisories table to store ingested
official weather forecasts, cyclone track polylines, and warning polygons.
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_forecast_advisories"
down_revision: Union[str, None] = "0005_weather_reports_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "forecast_advisories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_code", sa.String(length=50), nullable=False),
        sa.Column("hazard_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MODERATE"),
        sa.Column("advisory_title", sa.String(length=255), nullable=False),
        sa.Column("advisory_text", sa.Text(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="GEOMETRY",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_forecast_advisories_source",
        "forecast_advisories",
        ["source_code"],
    )
    op.create_index(
        "idx_forecast_advisories_hazard",
        "forecast_advisories",
        ["hazard_type"],
    )
    op.create_index(
        "idx_forecast_advisories_validity",
        "forecast_advisories",
        ["valid_until", "hazard_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_forecast_advisories_validity", table_name="forecast_advisories")
    op.drop_index("idx_forecast_advisories_hazard", table_name="forecast_advisories")
    op.drop_index("idx_forecast_advisories_source", table_name="forecast_advisories")
    op.drop_table("forecast_advisories")
