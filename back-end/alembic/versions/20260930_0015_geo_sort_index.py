"""Add partial geo-sort index on weather_reports for occurred_at DESC NULLS LAST.

The query in get_geo_incidents orders by:
    ORDER BY occurred_at DESC NULLS LAST, created_at DESC
with a WHERE geom IS NOT NULL filter.

The existing idx_weather_reports_occ_created (occurred_at DESC, created_at DESC)
does NOT carry NULLS LAST on occurred_at, so the planner falls back to a full
Seq Scan + top-N heapsort. This migration:

1. Creates a new partial index restricted to rows WHERE geom IS NOT NULL with
   the exact sort signature the geo query uses — enabling an Index Scan.
2. Drops the now-superseded idx_weather_reports_occ_created.

Note: CONCURRENTLY is omitted here because this migration runs inside a
transaction block managed by Alembic's async env.py. The table is small enough
that a regular (locking) CREATE INDEX is acceptable at migration time.

Revision identifiers, used by Alembic.
"""

import sqlalchemy as sa

from alembic import op

revision = "0015_geo_sort_index"
down_revision = "0014_backfill_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Partial index: exact match for the geo query WHERE + ORDER BY
    op.create_index(
        "idx_weather_reports_geo_sort",
        "weather_reports",
        [sa.text("occurred_at DESC NULLS LAST"), sa.text("created_at DESC")],
        postgresql_where=sa.text("geom IS NOT NULL"),
        if_not_exists=True,
    )

    # 2. Drop the old non-partial index (superseded — lacks NULLS LAST + partial predicate)
    op.drop_index(
        "idx_weather_reports_occ_created",
        table_name="weather_reports",
        if_exists=True,
    )


def downgrade() -> None:
    # Restore the old non-partial index
    op.create_index(
        "idx_weather_reports_occ_created",
        "weather_reports",
        [sa.text("occurred_at DESC"), sa.text("created_at DESC")],
        if_not_exists=True,
    )
    # Drop the new partial index
    op.drop_index(
        "idx_weather_reports_geo_sort",
        table_name="weather_reports",
        if_exists=True,
    )
