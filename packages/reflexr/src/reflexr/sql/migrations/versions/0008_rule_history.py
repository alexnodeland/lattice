"""Keep the stored rule each version fact is about in a column, so a rule's history is one range.

A stored rule's versions are its ``reflexr:rule_installed`` and ``reflexr:rule_archived`` facts
(ADR-0063). The column is filled from those facts' stored envelopes, whose ``event.rule`` is the
rule's name, in one statement that scans the log; every other row keeps it null, and the index
holds only the rows that have it. On PostgreSQL the statement and the index's build hold
``reflexr_events`` exclusively, inside the migration's transaction: run it when the log may
pause.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VERSIONS = ("reflexr:rule_installed", "reflexr:rule_archived")
"""The facts that are a stored rule's versions."""

_HAS_RULE = sa.text("rule IS NOT NULL")


def upgrade() -> None:
    """Upgrade the schema."""
    op.add_column("reflexr_events", sa.Column("rule", sa.String(), nullable=True))
    events = sa.table(
        "reflexr_events",
        sa.column("event_type", sa.String()),
        sa.column("envelope", sa.JSON()),
        sa.column("rule", sa.String()),
    )
    stored = events.c.envelope[("event", "rule")].as_string()
    op.execute(events.update().where(events.c.event_type.in_(_VERSIONS)).values(rule=stored))
    op.create_index(
        "ix_reflexr_events_rule",
        "reflexr_events",
        ["tenant_id", "workspace_id", "rule", "seq"],
        postgresql_where=_HAS_RULE,
        sqlite_where=_HAS_RULE,
    )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_index("ix_reflexr_events_rule", table_name="reflexr_events")
    # SQLite drops a column by copying the table, in batch mode.
    with op.batch_alter_table("reflexr_events") as batch:
        batch.drop_column("rule")
