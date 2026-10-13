"""Row-level security: each transaction tells PostgreSQL its tenant (lattice RFC-0001).

With the option on, [`SqlLedger`][relayr.sql.SqlLedger] opens its sessions as
`TenantSession`, which sets `SETTING` to its tenant, for the transaction only, as
the transaction begins. The policies the migrations create on PostgreSQL then show each
transaction only its tenant's rows. A pooled connection never carries a
tenant into its next transaction, and a session that names no tenant can't begin one.

lattice-core holds the tenant session, the policy and the grants, which every library's SQL
storage shares (lattice ADR-0018); this module re-exports them.
"""

from lattice_core.sql.tenancy import CURRENT_TENANT as CURRENT
from lattice_core.sql.tenancy import TENANT_KEY as TENANT
from lattice_core.sql.tenancy import TENANT_SETTING as SETTING
from lattice_core.sql.tenancy import TenantSession, grant, tenant_policy

__all__ = ["CURRENT", "SETTING", "TENANT", "TenantSession", "grant", "tenant_policy"]
