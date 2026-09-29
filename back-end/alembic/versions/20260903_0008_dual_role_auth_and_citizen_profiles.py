"""Add citizen profile columns to users, user_id to weather_reports and incident_feedback, and seed default admin/operator.

Revision ID: 0008_dual_role_auth
Revises: 0007_relief_centers_and_auth
Create Date: 2026-09-03 04:50:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.security import get_password_hash

# revision identifiers, used by Alembic.
revision = "0008_dual_role_auth"
down_revision = "0007_relief_centers_and_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add citizen location preferences and radius columns to users
    op.add_column("users", sa.Column("home_location_lat", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("home_location_lng", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("home_location_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("alert_radius_km", sa.Float(), nullable=True, server_default="25.0"))

    # 2. Add user_id foreign key to weather_reports (for citizen "My Reports")
    op.add_column(
        "weather_reports",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_weather_reports_user_id", "weather_reports", ["user_id"])

    # 3. Add user_id foreign key to incident_feedback (for citizen "My Votes")
    op.add_column(
        "incident_feedback",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_feedback_user_id", "incident_feedback", ["user_id"])

    # 4. Seed default Admin and Operator accounts
    admin_pwd = get_password_hash("EmergencyAdmin2026!")
    operator_pwd = get_password_hash("EmergencyOps2026!")

    op.execute(
        f"""
        INSERT INTO users (id, email, hashed_password, full_name, role, jurisdiction_code, is_active, created_at, updated_at)
        VALUES
        (
            '00000000-0000-0000-0000-000000000001'::uuid,
            'admin@weather-platform.gov.in',
            '{admin_pwd}',
            'Chief System Administrator',
            'ADMIN',
            'NATIONAL_HQ',
            true,
            NOW(),
            NOW()
        ),
        (
            'a1b2c3d4-e5f6-7890-abcd-1234567890ab'::uuid,
            'operator@weather-platform.gov.in',
            '{operator_pwd}',
            'National DEOC Lead Operator',
            'OPERATOR',
            'NATIONAL_DEOC',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (email) DO UPDATE
        SET hashed_password = EXCLUDED.hashed_password, role = EXCLUDED.role, is_active = true;
        """
    )


def downgrade() -> None:
    op.drop_index("idx_feedback_user_id", table_name="incident_feedback")
    op.drop_column("incident_feedback", "user_id")

    op.drop_index("idx_weather_reports_user_id", table_name="weather_reports")
    op.drop_column("weather_reports", "user_id")

    op.drop_column("users", "alert_radius_km")
    op.drop_column("users", "home_location_name")
    op.drop_column("users", "home_location_lng")
    op.drop_column("users", "home_location_lat")
