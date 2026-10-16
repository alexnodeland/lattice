"""A tenant's transaction may add the deployment log's one entry about the tenant it creates.

Creating a tenant is recorded in the deployment's audit log as well as the tenant's, in the same
transaction, which names the new tenant and so can add only that tenant's rows. One policy lets
it add one more row, for ``INSERT`` alone: a deployment entry of the type
``deployment_tenant_created``, whose event names the transaction's own tenant, which must be
named. No other command and no other deployment entry is allowed, and the deployment's audit rows
stay unreadable, so the application's role cannot read, change or delete them. PostgreSQL only.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = "grantr_audit_tenant_creation"

CURRENT = "current_setting('lattice.tenant_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        f"CREATE POLICY {POLICY} ON grantr_audit FOR INSERT WITH CHECK ("
        " tenant_id = '~deployment'"
        f" AND {CURRENT} <> ''"
        " AND event_type = 'deployment_tenant_created'"
        " AND body #>> '{event,type}' = 'deployment_tenant_created'"
        f" AND body #>> '{{event,tenant}}' = {CURRENT}"
        ")"
    )


def downgrade() -> None:
    """Downgrade the schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DROP POLICY {POLICY} ON grantr_audit")
