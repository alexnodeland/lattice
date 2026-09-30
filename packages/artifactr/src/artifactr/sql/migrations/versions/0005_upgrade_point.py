"""Record where each workspace's log stood at this upgrade, so its threads start from there.

The runner takes a thread's messages from the log (ADR-0055). A thread from before this
upgrade has no position of its own yet, so its messages up to here count as taken: nothing
older resurfaces as a turn. The cursor's name is the runner's ``_UPGRADED``, in
``artifactr.agent.runner``; a migration is a snapshot, so it does not import it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADED = "artifactr.runner/upgraded"

_workspaces = sa.table(
    "artifactr_workspaces",
    sa.column("tenant_id", sa.String()),
    sa.column("workspace_id", sa.String()),
    sa.column("head_seq", sa.BigInteger()),
)
_cursors = sa.table(
    "artifactr_cursors",
    sa.column("tenant_id", sa.String()),
    sa.column("workspace_id", sa.String()),
    sa.column("name", sa.String()),
    sa.column("seq", sa.BigInteger()),
)


def upgrade() -> None:
    """Record each workspace's head as the point its threads start from."""
    heads = sa.select(
        _workspaces.c.tenant_id,
        _workspaces.c.workspace_id,
        sa.literal(UPGRADED),
        _workspaces.c.head_seq,
    )
    op.execute(_cursors.insert().from_select(["tenant_id", "workspace_id", "name", "seq"], heads))


def downgrade() -> None:
    """Forget the points."""
    op.execute(_cursors.delete().where(_cursors.c.name == UPGRADED))
