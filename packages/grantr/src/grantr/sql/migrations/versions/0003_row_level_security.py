"""Row-level security on PostgreSQL: each tenant's rows, and the deployment's grants to read.

The policies hold for every role but the tables' owner, which the migrations run as and the
reads across tenants use: they are enabled, not forced. A transaction sees, changes and adds
only the rows of the tenant ``lattice.tenant_id`` names, and reads the deployment's grants and
group members besides, which every check may need. One that names no tenant sees nothing.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = {
    "grantr_tenants": "id",
    "grantr_grants": "tenant_id",
    "grantr_resources": "tenant_id",
    "grantr_groups": "tenant_id",
    "grantr_group_members": "tenant_id",
    "grantr_roles": "tenant_id",
    "grantr_keys": "tenant_id",
    "grantr_audit": "tenant_id",
}
"""Each table, and the column that names its tenant."""

DEPLOYMENT_READS = ("grantr_grants", "grantr_group_members")
"""The tables whose deployment rows every tenant reads."""

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column in TABLES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table}"
            f" USING ({column} = {CURRENT}) WITH CHECK ({column} = {CURRENT})"
        )
    for table in DEPLOYMENT_READS:
        op.execute(
            f"CREATE POLICY {table}_deployment ON {table} FOR SELECT"
            f" USING (tenant_id = '~deployment' AND {CURRENT} <> '')"
        )


def downgrade() -> None:
    """Downgrade the schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in DEPLOYMENT_READS:
        op.execute(f"DROP POLICY {table}_deployment ON {table}")
    for table in TABLES:
        op.execute(f"DROP POLICY {table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
