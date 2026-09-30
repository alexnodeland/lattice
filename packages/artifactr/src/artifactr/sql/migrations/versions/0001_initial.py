"""The initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITIES = ("artifacts", "proposals", "threads", "runs")


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        "artifactr_workspaces",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("head_seq", sa.BigInteger(), nullable=False),
        sa.Column("last_position", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "workspace_id", name=op.f("pk_artifactr_workspaces")),
    )
    op.create_table(
        "artifactr_artifacts",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "id", name=op.f("pk_artifactr_artifacts")
        ),
    )
    op.create_table(
        "artifactr_revisions",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "workspace_id",
            "artifact_id",
            "version",
            name=op.f("pk_artifactr_revisions"),
        ),
    )
    op.create_table(
        "artifactr_proposals",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "id", name=op.f("pk_artifactr_proposals")
        ),
    )
    op.create_table(
        "artifactr_threads",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "id", name=op.f("pk_artifactr_threads")
        ),
    )
    op.create_table(
        "artifactr_runs",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "workspace_id", "id", name=op.f("pk_artifactr_runs")),
    )
    for entity in _ENTITIES:
        op.create_index(
            f"ix_artifactr_{entity}_position",
            f"artifactr_{entity}",
            ["tenant_id", "workspace_id", "position"],
        )
    op.create_table(
        "artifactr_events",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "seq", name=op.f("pk_artifactr_events")
        ),
    )
    op.create_table(
        "artifactr_history",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("messages", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "position", name=op.f("pk_artifactr_history")
        ),
    )
    op.create_index(
        "ix_artifactr_history_thread",
        "artifactr_history",
        ["tenant_id", "workspace_id", "thread_id", "position"],
    )
    op.create_table(
        "artifactr_leases",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("holder", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "workspace_id", "key", name=op.f("pk_artifactr_leases")
        ),
    )


def downgrade() -> None:
    """Downgrade the schema."""
    for table in ("leases", "history", "events", *_ENTITIES, "revisions", "workspaces"):
        op.drop_table(f"artifactr_{table}")
