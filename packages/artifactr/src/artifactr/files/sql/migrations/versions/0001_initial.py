"""The initial schema: blobs and check-outs, each row kept to its tenant on PostgreSQL.

The policies hold for every role but the tables' owner, which the migrations run as: they are
enabled, not forced. Blobs' bytes are stored out of line and uncompressed.

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("artifactr_files_blobs", "artifactr_files_checkouts")
"""Every table: each names its tenant in ``tenant_id``."""

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        "artifactr_files_blobs",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("last_put", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "workspace_id",
            "artifact_id",
            "sha256",
            name=op.f("pk_artifactr_files_blobs"),
        ),
    )
    op.create_table(
        "artifactr_files_checkouts",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("base_version", sa.BigInteger(), nullable=False),
        sa.Column("base_sha256", sa.String(), nullable=False),
        sa.Column("actor", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_in", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "id", name=op.f("pk_artifactr_files_checkouts")
        ),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE artifactr_files_blobs ALTER COLUMN data SET STORAGE EXTERNAL")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table}"
            f" USING (tenant_id = {CURRENT}) WITH CHECK (tenant_id = {CURRENT})"
        )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_table("artifactr_files_checkouts")
    op.drop_table("artifactr_files_blobs")
