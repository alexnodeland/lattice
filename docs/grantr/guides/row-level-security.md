# Row-level security

grantr's SQL storage, and artifactr's, reflexr's and relayr's, scope every query to a tenant themselves. With PostgreSQL's row-level security on as well, PostgreSQL keeps tenants apart even if one of those queries were scoped wrongly ([lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md#row-level-security), [ADR-0026](../adr/0026-row-level-security-under-the-scoping.md)).

## How it works

- **Each transaction names its tenant.** With `SqlStorage(..., row_level_security=True)`, every transaction sets `lattice.tenant_id` as it begins, for itself only, so a pooled connection never carries a tenant on. A session that names no tenant can't begin one.
- **The policies keep it there.** The migrations create a policy on every table, enabled and not forced: a transaction reads, changes and adds only its tenant's rows, and grantr's tenants also read the deployment's rows of `grantr_grants` and `grantr_group_members`, which their checks need. A transaction that names no tenant sees nothing.
- **The policies apply to every role except the tables' owner,** so the application works as a role that owns nothing, and the owner migrates the tables and grants that role them: `migrate(owner_engine, application_role="app")`.
- **A few reads span tenants,** and go to the owner's engine, `across_tenants`, and nothing else does: in grantr, finding a key's tenant, a user's memberships and the tenants' list; reflexr's dispatcher and scheduler; relayr's followers' start.

```python title="Illustrative: needs PostgreSQL"
from sqlalchemy.ext.asyncio import create_async_engine

from grantr import Grants
from grantr.sql import SqlStorage, migrate

owner = create_async_engine("postgresql+asyncpg://postgres:…@db/app")
await migrate(owner, application_role="app")  # the role must exist first
engine = create_async_engine("postgresql+asyncpg://app:…@db/app")
grants = Grants(
    SqlStorage(engine, row_level_security=True, across_tenants=owner), catalogs=[ARTIFACTR, REFLEXR]
)
```

reflexr's `SqlStorage` and relayr's `SqlLedger` take the same two options. artifactr's `SqlStorage` takes `row_level_security` but no `across_tenants`, since none of its reads span tenants ([artifactr ADR-0066](../../artifactr/adr/0066-row-level-security-under-the-scoping.md), [reflexr ADR-0062](../../reflexr/adr/0062-row-level-security-under-the-scoping.md), [relayr ADR-0027](../../relayr/adr/0027-row-level-security-under-the-scoping.md)).

## In stackr's template

The template turns it on with a second URL ([stackr ADR-0022](../../stackr/adr/0022-row-level-security-in-the-template.md)):

| Setting | The role |
|---|---|
| `DATABASE_URL` | The one the application works as, which owns nothing, such as `my_app_app`; its name and password are this URL's |
| `DATABASE_ADMIN_URL` | The tables' owner, which migrates them and reads across tenants |

1. **Create the role** with `make db-roles`, as the owner, before the application first starts. It creates `DATABASE_URL`'s role, or sets its password again, sending the password only as a SCRAM-SHA-256 verifier. It runs on its own too, as a one-off task beside a deployment.
2. **Start the application.** It migrates as the owner, granting the role the libraries' tables, and works as the role.

The application refuses to start as a role the policies don't hold: one named in both URLs, a superuser, one that bypasses row-level security, or one that owns the schema or is a member of its owner's role. Without `DATABASE_ADMIN_URL`, nothing changes: one URL, as the tables' owner.

The running application keeps the owner's URL, for the migrations it runs as it starts and the reads across tenants, so row-level security guards against a query scoped wrongly, not against a compromised application.
