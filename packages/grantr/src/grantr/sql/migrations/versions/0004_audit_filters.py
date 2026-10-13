"""The audit log's filters: each entry's event type and maker, in indexed columns.

The columns are added, filled from each entry's JSON a thousand entries at a time, and then
required. The maker is stored as a grant's subject is: its kind, workspace and id, ``""`` for a
part it doesn't have, and ``""`` in all three for the first operator, whom no one granted. The
migrations run as the tables' owner, which row-level security doesn't hold, so every tenant's
entries are filled. ``grantr_audit`` is held exclusively until the migration commits.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHUNK = 1000
"""How many entries one batch of updates fills."""

AUDIT = sa.table(
    "grantr_audit",
    sa.column("seq", sa.BigInteger()),
    sa.column("body", sa.JSON()),
    sa.column("event_type", sa.String()),
    sa.column("actor_kind", sa.String()),
    sa.column("actor_workspace", sa.String()),
    sa.column("actor_id", sa.String()),
)

COLUMNS = ("event_type", "actor_kind", "actor_workspace", "actor_id")

FILL = (
    AUDIT.update()
    .where(AUDIT.c.seq == sa.bindparam("entry"))
    .values({name: sa.bindparam(f"new_{name}") for name in COLUMNS})
)
"""One entry's columns, by its sequence number: run once for a whole chunk of entries."""


def _maker(by: dict[str, Any] | None) -> tuple[str, str, str]:
    """An entry's maker's columns, from its JSON, as subjects were stored when this was written.

    It is kept here, so the migration fills what it filled then, whatever the code becomes.

    Raises:
        ValueError: For a maker of a kind no audit entry could have had.
    """
    match by:
        case None:
            return ("", "", "")
        case {"kind": "user" | "service_principal" as kind, "id": str(id)}:
            return (kind, "", id)
        case {"kind": "rule", "workspace": str(workspace), "rule": str(rule)}:
            return ("rule", workspace, rule)
        case {"kind": "agent"}:
            return ("agent", "", "")
        case _:
            raise ValueError(f"an audit entry's maker of no known kind: {by!r}")


def _filled(seq: int, body: dict[str, Any]) -> dict[str, Any]:
    """One entry's columns, as ``FILL`` binds them."""
    kind, workspace, id = _maker(body.get("by"))
    return {
        "entry": seq,
        "new_event_type": body["event"]["type"],
        "new_actor_kind": kind,
        "new_actor_workspace": workspace,
        "new_actor_id": id,
    }


def upgrade() -> None:
    """Upgrade the schema."""
    with op.batch_alter_table("grantr_audit") as batch:
        for name in COLUMNS:
            batch.add_column(sa.Column(name, sa.String(), nullable=True))
    bind = op.get_bind()
    after = 0
    # A chunk at a time, after the last one's sequence number, so no cursor stays open while
    # its entries are updated.
    while chunk := bind.execute(
        sa.select(AUDIT.c.seq, AUDIT.c.body)
        .where(AUDIT.c.seq > after)
        .order_by(AUDIT.c.seq)
        .limit(CHUNK)
    ).all():
        bind.execute(FILL, [_filled(seq, body) for seq, body in chunk])
        after = chunk[-1].seq
    with op.batch_alter_table("grantr_audit") as batch:
        for name in COLUMNS:
            batch.alter_column(name, existing_type=sa.String(), nullable=False)
    op.create_index(
        "ix_grantr_audit_event_type", "grantr_audit", ["tenant_id", "event_type", "seq"]
    )
    op.create_index(
        "ix_grantr_audit_actor",
        "grantr_audit",
        ["tenant_id", "actor_kind", "actor_workspace", "actor_id", "seq"],
    )


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_index("ix_grantr_audit_actor", table_name="grantr_audit")
    op.drop_index("ix_grantr_audit_event_type", table_name="grantr_audit")
    with op.batch_alter_table("grantr_audit") as batch:
        for name in reversed(COLUMNS):
            batch.drop_column(name)
