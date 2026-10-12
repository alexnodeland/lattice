"""Row-level security on PostgreSQL: each transaction sees only its tenant's rows.

The policies hold for every role but the tables' owner, which the migrations run as, and the
reads across tenants use: they are enabled, not forced. A transaction sees, changes and adds only
the rows of the tenant ``lattice.tenant_id`` names, and one that names no tenant, or an empty
one, sees nothing.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "reflexr_workspaces",
    "reflexr_events",
    "reflexr_runs",
    "reflexr_rule_progress",
    "reflexr_scope_states",
    "reflexr_dead_letters",
    "reflexr_schedules",
    "reflexr_leases",
    "reflexr_cursors",
    "reflexr_rules",
)
"""Every table: each names its tenant in ``tenant_id``."""

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table}"
            f" USING (tenant_id = {CURRENT}) WITH CHECK (tenant_id = {CURRENT})"
        )


def downgrade() -> None:
    """Downgrade the schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"DROP POLICY {table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
