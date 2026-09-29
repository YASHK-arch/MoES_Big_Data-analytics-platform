"""Add expanded weather categories seed and migration.

Revision ID: 0009_expanded_categories
Revises: 0008_dual_role_auth
Create Date: 2026-09-30 04:20:00.000000
"""

import uuid

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_expanded_categories"
down_revision = "0008_dual_role_auth"
branch_labels = None
depends_on = None

CATEGORIES = [
    {
        "category_code": "FLOOD_WATERLOGGING",
        "title": "Flooding & Waterlogging",
        "severity_default": "HIGH",
        "color_hex": "#3b82f6",
        "icon_name": "droplets",
    },
    {
        "category_code": "HEAVY_RAINFALL",
        "title": "Heavy Rainfall",
        "severity_default": "HIGH",
        "color_hex": "#2563eb",
        "icon_name": "cloud-rain",
    },
    {
        "category_code": "THUNDERSTORM_LIGHTNING",
        "title": "Thunderstorm & Lightning",
        "severity_default": "HIGH",
        "color_hex": "#eab308",
        "icon_name": "zap",
    },
    {
        "category_code": "CYCLONE_STORM",
        "title": "Cyclone & Storm",
        "severity_default": "SEVERE",
        "color_hex": "#7c3aed",
        "icon_name": "wind",
    },
    {
        "category_code": "HEATWAVE",
        "title": "Heatwave",
        "severity_default": "HIGH",
        "color_hex": "#ef4444",
        "icon_name": "thermometer-sun",
    },
    {
        "category_code": "HAILSTORM",
        "title": "Hailstorm",
        "severity_default": "HIGH",
        "color_hex": "#06b6d4",
        "icon_name": "cloud-hail",
    },
    {
        "category_code": "LANDSLIDE",
        "title": "Landslide & Mudslip",
        "severity_default": "SEVERE",
        "color_hex": "#b45309",
        "icon_name": "mountain",
    },
    {
        "category_code": "DROUGHT",
        "title": "Drought Condition",
        "severity_default": "MODERATE",
        "color_hex": "#d97706",
        "icon_name": "sun",
    },
    {
        "category_code": "URBAN_FLOOD",
        "title": "Urban Inundation",
        "severity_default": "HIGH",
        "color_hex": "#0284c7",
        "icon_name": "waves",
    },
    {
        "category_code": "FOG",
        "title": "Dense Fog",
        "severity_default": "MODERATE",
        "color_hex": "#64748b",
        "icon_name": "cloud-fog",
    },
    {
        "category_code": "DUST_STORM",
        "title": "Dust Storm",
        "severity_default": "HIGH",
        "color_hex": "#a16207",
        "icon_name": "sparkles",
    },
    {
        "category_code": "STRONG_WIND",
        "title": "Strong Wind & Gale",
        "severity_default": "HIGH",
        "color_hex": "#0d9488",
        "icon_name": "wind",
    },
    {
        "category_code": "OTHER",
        "title": "Other Weather Hazard",
        "severity_default": "LOW",
        "color_hex": "#6b7280",
        "icon_name": "alert-triangle",
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Update legacy codes in event_categories and weather_reports
    conn.execute(
        sa.text(
            "UPDATE weather_reports SET reported_category = 'CYCLONE_STORM' WHERE reported_category = 'CYCLONE_GALE';"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE weather_reports SET reported_category = 'HEATWAVE' WHERE reported_category = 'EXTREME_HEAT';"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE event_categories SET category_code = 'CYCLONE_STORM', title = 'Cyclone & Storm' WHERE category_code = 'CYCLONE_GALE';"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE event_categories SET category_code = 'HEATWAVE', title = 'Heatwave' WHERE category_code = 'EXTREME_HEAT';"
        )
    )

    # 2. Insert or update canonical categories
    for cat in CATEGORIES:
        cat_id = str(uuid.uuid4())
        conn.execute(
            sa.text("""
                INSERT INTO event_categories (id, category_code, title, severity_default, color_hex, icon_name)
                VALUES (:id, :code, :title, :sev, :col, :icon)
                ON CONFLICT (category_code) DO UPDATE
                SET title = EXCLUDED.title,
                    severity_default = EXCLUDED.severity_default,
                    color_hex = EXCLUDED.color_hex,
                    icon_name = EXCLUDED.icon_name;
            """),
            {
                "id": cat_id,
                "code": cat["category_code"],
                "title": cat["title"],
                "sev": cat["severity_default"],
                "col": cat["color_hex"],
                "icon": cat["icon_name"],
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM event_categories WHERE category_code IN ('FOG', 'DUST_STORM', 'STRONG_WIND', 'DROUGHT', 'URBAN_FLOOD');"
        )
    )
