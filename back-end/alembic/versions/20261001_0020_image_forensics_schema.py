"""create image_hashes and incident_image_findings tables

Revision ID: 0020_image_forensics
Revises: 0019_physical_corroboration
Create Date: 2026-10-01 02:40:00.000000+00:00

Scaling Limit & Design Documentation:
- Exact hash matches: O(log N) lookup using B-Tree index on `sha256` and `phash`.
- Nearest-neighbor Hamming distance lookup (distance <= threshold):
  Currently performs exact-prefix candidate filtering combined with application-level
  Hamming filtering over candidate buckets.
  Scaling limit: This approach scales well up to ~1,000,000 images (< 15ms).
  For datasets exceeding 1,000,000 images, dedicated Hamming distance index extensions
  (e.g., pgvector binary hamming bit(64) with HNSW, or external VP-tree indexing)
  must be introduced.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_image_forensics"
down_revision: Union[str, None] = "0019_physical_corroboration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create table image_hashes
    op.create_table(
        "image_hashes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("phash", sa.String(length=16), nullable=False),
        sa.Column("dhash", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["weather_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["report_media.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_image_hashes_phash", "image_hashes", ["phash"], unique=False)
    op.create_index("idx_image_hashes_sha256", "image_hashes", ["sha256"], unique=False)
    op.create_index("idx_image_hashes_incident_id", "image_hashes", ["incident_id"], unique=False)
    op.create_index("idx_image_hashes_media_id", "image_hashes", ["media_id"], unique=False)

    # 2. Create table incident_image_findings
    op.create_table(
        "incident_image_findings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("phash", sa.String(length=16), nullable=False),
        sa.Column("dhash", sa.String(length=16), nullable=False),
        sa.Column("has_exif", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("exif_timestamp_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "timezone_assumed_ist",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "time_verdict",
            sa.String(length=20),
            server_default=sa.text("'NEUTRAL'"),
            nullable=False,
        ),
        sa.Column("time_difference", sa.String(length=50), nullable=True),
        sa.Column(
            "location_verdict",
            sa.String(length=20),
            server_default=sa.text("'NEUTRAL'"),
            nullable=False,
        ),
        sa.Column("location_difference", sa.String(length=50), nullable=True),
        sa.Column(
            "reuse_verdict",
            sa.String(length=20),
            server_default=sa.text("'NEUTRAL'"),
            nullable=False,
        ),
        sa.Column(
            "matched_incident_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        sa.Column(
            "overall_verdict",
            sa.String(length=20),
            server_default=sa.text("'NEUTRAL'"),
            nullable=False,
        ),
        sa.Column("credibility_adjustment", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_reason", sa.String(length=255), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["weather_reports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["report_media.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_incident_image_findings_incident",
        "incident_image_findings",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "idx_incident_image_findings_media",
        "incident_image_findings",
        ["media_id"],
        unique=False,
    )
    op.create_index(
        "idx_incident_image_findings_phash",
        "incident_image_findings",
        ["phash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_incident_image_findings_phash", table_name="incident_image_findings")
    op.drop_index("idx_incident_image_findings_media", table_name="incident_image_findings")
    op.drop_index("idx_incident_image_findings_incident", table_name="incident_image_findings")
    op.drop_table("incident_image_findings")

    op.drop_index("idx_image_hashes_media_id", table_name="image_hashes")
    op.drop_index("idx_image_hashes_incident_id", table_name="image_hashes")
    op.drop_index("idx_image_hashes_sha256", table_name="image_hashes")
    op.drop_index("idx_image_hashes_phash", table_name="image_hashes")
    op.drop_table("image_hashes")
