"""The audit log's filters: each entry's event type and actor, in indexed columns.

The columns are filled from each entry's JSON, then the type is required. The migrations run as
the tables' owner, which row-level security doesn't hold, so every tenant's entries are filled.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT = sa.table(
    "grantr_audit",
    sa.column("seq", sa.BigInteger()),
    sa.column("body", sa.JSON()),
    sa.column("event_type", sa.String()),
    sa.column("actor", sa.String()),
)


def _actor(by: dict[str, Any] | None) -> str | None:
    """Who made an entry, as ``grantr.core.actor_of`` named them when this was written.

    It is kept here, so the migration fills what it filled then, whatever the code becomes.
    """
    match by:
        case None:
            return None
        case {"kind": "user" | "service_principal" as kind, "id": id}:
            return f"{kind}:{id}"
        case {"kind": "rule", "workspace": workspace, "rule": rule}:
            return f"rule:{workspace}/{rule}"
        case _:
            return "agent"


def _filled(body: dict[str, Any]) -> dict[str, Any]:
    """An entry's type and actor, from its JSON."""
    return {"event_type": body["event"]["type"], "actor": _actor(body.get("by"))}


def upgrade() -> None:
    """Upgrade the schema."""
    with op.batch_alter_table("grantr_audit") as batch:
        batch.add_column(sa.Column("event_type", sa.String(), nullable=True))
        batch.add_column(sa.Column("actor", sa.String(), nullable=True))
    bind = op.get_bind()
    for seq, body in bind.execute(sa.select(AUDIT.c.seq, AUDIT.c.body)).all():
        bind.execute(AUDIT.update().where(AUDIT.c.seq == seq).values(**_filled(body)))
    with op.batch_alter_table("grantr_audit") as batch:
        batch.alter_column("event_type", existing_type=sa.String(), nullable=False)
    op.create_index("ix_grantr_audit_type", "grantr_audit", ["tenant_id", "event_type", "seq"])
    op.create_index("ix_grantr_audit_actor", "grantr_audit", ["tenant_id", "actor", "seq"])


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_index("ix_grantr_audit_actor", table_name="grantr_audit")
    op.drop_index("ix_grantr_audit_type", table_name="grantr_audit")
    with op.batch_alter_table("grantr_audit") as batch:
        batch.drop_column("actor")
        batch.drop_column("event_type")
