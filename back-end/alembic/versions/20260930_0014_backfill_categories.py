"""Insert missing event_categories and backfill weather_reports.category_id.

Revision ID: 0014_backfill_categories
Revises: 0013_drop_duplicate_indexes
Create Date: 2026-09-30 11:00:00.000000
"""

import uuid
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0014_backfill_categories"
down_revision = "0013_drop_duplicate_indexes"
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

    # 1. Insert any missing canonical event_categories rows
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

    # 2. Backfill weather_reports.category_id from reported_category where category_id IS NULL

    # 2a. Direct match on category_code
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) = ec.category_code;
        """)
    )

    # 2b. Direct match on title
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) = UPPER(TRIM(ec.title));
        """)
    )

    # 2c. Known legacy aliases
    # CYCLONE_STORM
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'CYCLONE_STORM'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN (
                  'CYCLONE', 'CYCLONE_GALE', 'CYCLONE_HIGH_WIND', 'CYCLONE_STORM_SURGE', 'GALE', 'STORM'
              );
        """)
    )

    # HEATWAVE
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'HEATWAVE'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN ('EXTREME_HEAT', 'HEAT');
        """)
    )

    # FLOOD_WATERLOGGING
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'FLOOD_WATERLOGGING'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN ('FLOOD', 'FL', 'WATERLOGGING', 'WATERLOG', 'FLOODING');
        """)
    )

    # URBAN_FLOOD
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'URBAN_FLOOD'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN ('URBAN_FLOODING', 'CITY_FLOOD');
        """)
    )

    # FOG
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'FOG'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN ('DENSE_FOG', 'AIR_QUALITY_SMOG', 'SMOG', 'MIST');
        """)
    )

    # HEAVY_RAINFALL
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'HEAVY_RAINFALL'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN ('RAIN', 'RAINFALL', 'DOWNPOUR', 'CLOUDBURST');
        """)
    )

    # DUST_STORM
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'DUST_STORM'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN ('SANDSTORM', 'DUST');
        """)
    )

    # STRONG_WIND
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'STRONG_WIND'
              AND wr.reported_category IS NOT NULL
              AND UPPER(TRIM(wr.reported_category)) IN ('HIGH_WIND', 'GUST', 'WIND');
        """)
    )

    # 2d. Default fallback to OTHER for remaining NULLs (including synthetic CAT_ codes or NULL reported_category)
    conn.execute(
        sa.text("""
            UPDATE weather_reports wr
            SET category_id = ec.id
            FROM event_categories ec
            WHERE wr.category_id IS NULL
              AND ec.category_code = 'OTHER';
        """)
    )


def downgrade() -> None:
    # Downgrade is a safe no-op since setting category_id to NULL would destroy valid relational links.
    # If explicit rollback is requested, rows backfilled to OTHER can be reset if needed.
    pass
