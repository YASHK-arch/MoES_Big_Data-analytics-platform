"""create incident_physical_corroboration table

Revision ID: 0019_physical_corroboration
Revises: 0018_archive_metadata
Create Date: 2026-10-01 01:25:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_physical_corroboration"
down_revision: Union[str, None] = "0018_archive_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incident_physical_corroboration",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variable", sa.String(length=50), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("station_or_grid_id", sa.String(length=100), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("time_gap_h", sa.Float(), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("weight", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("contribution", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column(
            "provider_status", sa.String(length=50), server_default=sa.text("'OK'"), nullable=False
        ),
        sa.Column("observation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["weather_reports.id"],
            name="fk_physical_corrob_incident_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_incident_physical_corroboration"),
        sa.UniqueConstraint(
            "incident_id",
            "variable",
            "source",
            "observation_time",
            name="uq_physical_corrob_incident_var_source_time",
        ),
    )
    op.create_index(
        "idx_physical_corrob_incident_id",
        "incident_physical_corroboration",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "idx_physical_corrob_verdict",
        "incident_physical_corroboration",
        ["verdict"],
        unique=False,
    )
    op.create_index(
        "idx_physical_corrob_source_time",
        "incident_physical_corroboration",
        ["source", "observation_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_physical_corrob_source_time", table_name="incident_physical_corroboration")
    op.drop_index("idx_physical_corrob_verdict", table_name="incident_physical_corroboration")
    op.drop_index("idx_physical_corrob_incident_id", table_name="incident_physical_corroboration")
    op.drop_table("incident_physical_corroboration")
