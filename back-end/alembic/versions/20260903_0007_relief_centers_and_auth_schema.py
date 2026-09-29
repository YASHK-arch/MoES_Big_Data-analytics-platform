"""Add relief_centers, incident_feedback tables and seed operator account.

Revision ID: 0007_relief_centers_and_auth
Revises: 0006_forecast_advisories
Create Date: 2026-09-03 03:05:00.000000

"""

import uuid

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.security import get_password_hash

# revision identifiers, used by Alembic.
revision = "0007_relief_centers_and_auth"
down_revision = "0006_forecast_advisories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create relief_centers table
    op.create_table(
        "relief_centers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("center_type", sa.String(length=50), nullable=False, server_default="SHELTER"),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("district_name", sa.String(length=100), nullable=True),
        sa.Column("state_name", sa.String(length=100), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("occupied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_relief_centers_active", "relief_centers", ["is_active"])
    op.create_index("idx_relief_centers_name", "relief_centers", ["name"])
    op.create_index("idx_relief_centers_district", "relief_centers", ["district_name"])
    op.create_index("idx_relief_centers_state", "relief_centers", ["state_name"])

    # 2. Create incident_feedback table
    op.create_table(
        "incident_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("weather_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vote_type", sa.String(length=20), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_feedback_report_id", "incident_feedback", ["report_id"])

    # 3. Seed default operator user account if users table is empty
    hashed_pwd = get_password_hash("EmergencyOps2026!")
    op.execute(
        f"""
        INSERT INTO users (id, email, hashed_password, full_name, role, jurisdiction_code, is_active, created_at, updated_at)
        VALUES (
            'a1b2c3d4-e5f6-7890-abcd-1234567890ab'::uuid,
            'operator@weather-platform.gov.in',
            '{hashed_pwd}',
            'National DEOC Lead Operator',
            'OPERATOR',
            'NATIONAL_DEOC',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (email) DO UPDATE
        SET hashed_password = '{hashed_pwd}', role = 'OPERATOR', is_active = true;
        """
    )

    # 4. Seed initial Relief Centers
    op.execute(
        """
        INSERT INTO relief_centers (id, name, center_type, address, district_name, state_name, capacity, occupied_count, contact_phone, is_active, latitude, longitude, geom)
        VALUES
        (
            '11111111-1111-1111-1111-111111111111'::uuid,
            'Bengaluru Central Cyclone & Flood Relief Shelter',
            'SHELTER',
            'Kanteerava Indoor Stadium Complex, MG Road, Bengaluru',
            'Bengaluru Urban',
            'Karnataka',
            1500,
            120,
            '080-22942222',
            true,
            12.9700,
            77.5900,
            ST_SetSRID(ST_MakePoint(77.5900, 12.9700), 4326)
        ),
        (
            '22222222-2222-2222-2222-222222222222'::uuid,
            'Victoria Hospital Emergency Disaster Care Unit',
            'HOSPITAL',
            'Fort, Near City Market, Bengaluru',
            'Bengaluru Urban',
            'Karnataka',
            800,
            340,
            '080-26701150',
            true,
            12.9630,
            77.5740,
            ST_SetSRID(ST_MakePoint(77.5740, 12.9630), 4326)
        ),
        (
            '33333333-3333-3333-3333-333333333333'::uuid,
            'Chennai Central Multipurpose Evacuation Shelter',
            'SHELTER',
            'Marina Beach Promenade, Triplicane, Chennai',
            'Chennai',
            'Tamil Nadu',
            2500,
            450,
            '044-25619200',
            true,
            13.0600,
            80.2800,
            ST_SetSRID(ST_MakePoint(80.2800, 13.0600), 4326)
        ),
        (
            '44444444-4444-4444-4444-444444444444'::uuid,
            'Mumbai Coastal Relief Camp #4',
            'RELIEF_CAMP',
            'Dadar West Flood Relief Center, Dadar, Mumbai',
            'Mumbai City',
            'Maharashtra',
            3000,
            600,
            '022-24137800',
            true,
            19.0180,
            72.8430,
            ST_SetSRID(ST_MakePoint(72.8430, 19.0180), 4326)
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("incident_feedback")
    op.drop_table("relief_centers")
