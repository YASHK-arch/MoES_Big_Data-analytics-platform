"""Weather Reports Archive Schema for Cold-Storage Historical Analytics

Revision ID: 0005_weather_reports_archive
Revises: 0004_realtime_outbox_schema
Create Date: 2026-09-03 01:00:00.000000+00:00

Additive migration creating the weather_reports_archive table to persist
verified reports upon retention window expiration.
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_weather_reports_archive"
down_revision: Union[str, None] = "0004_realtime_outbox_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create weather_reports_archive table
    op.create_table(
        "weather_reports_archive",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tracking_id", sa.String(32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reported_category", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), server_default="MODERATE", nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location_name", sa.String(255), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_status", sa.String(30), server_default="PROCESSED", nullable=False),
        sa.Column("verification_status", sa.String(30), server_default="VERIFIED", nullable=False),
        sa.Column("credibility_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("credibility_explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("text_embedding", sa.ARRAY(sa.Float()), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("original_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 2. Create spatial index
    op.create_index(
        "idx_weather_reports_archive_geom",
        "weather_reports_archive",
        ["geom"],
        postgresql_using="gist",
    )

    # 3. Create btree indexes
    op.create_index(
        "idx_weather_reports_archive_tracking_id",
        "weather_reports_archive",
        ["tracking_id"],
    )
    op.create_index(
        "idx_weather_reports_archive_occurred_at",
        "weather_reports_archive",
        ["occurred_at"],
    )
    op.create_index(
        "idx_weather_reports_archive_status_time",
        "weather_reports_archive",
        ["verification_status", "occurred_at"],
    )
    op.create_index(
        "idx_weather_reports_archive_credibility",
        "weather_reports_archive",
        ["credibility_score"],
    )
    op.create_index(
        "idx_weather_reports_archive_source_external",
        "weather_reports_archive",
        ["source_id", "external_id"],
    )
    op.create_index(
        "idx_weather_reports_archive_archived_at",
        "weather_reports_archive",
        ["archived_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_weather_reports_archive_archived_at", table_name="weather_reports_archive")
    op.drop_index("idx_weather_reports_archive_source_external", table_name="weather_reports_archive")
    op.drop_index("idx_weather_reports_archive_credibility", table_name="weather_reports_archive")
    op.drop_index("idx_weather_reports_archive_status_time", table_name="weather_reports_archive")
    op.drop_index("idx_weather_reports_archive_occurred_at", table_name="weather_reports_archive")
    op.drop_index("idx_weather_reports_archive_tracking_id", table_name="weather_reports_archive")
    op.drop_index("idx_weather_reports_archive_geom", table_name="weather_reports_archive")
    op.drop_table("weather_reports_archive")
