# ADR-0031: The catalog, read

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

portalr's admin grants roles and defines a tenant's own (lattice RFC-0002). Granting needs the roles a resource of each kind may be granted. Defining a custom role needs the actions it may hold. grantr holds both, in the catalog it builds from the libraries' catalogs: each built-in role's actions, by the level it is granted at, and a workspace's admin's actions, which a custom role may hold some of. It read neither out. `GET /roles` reads a tenant's custom roles alone.

The maintainer chose to read the catalog from grantr rather than copy it into the browser, where it would drift from the catalogs an application hands grantr.

## Decision

- **`Catalog.view()` answers a `CatalogView`:**
  - **`roles`:** each built-in role granted within a tenant, with the kinds of resource it may be granted on, in the order of where it is granted. A role granted at the item level may be granted on a thread, an artifact or a rule.
  - **`custom_actions`:** the actions a custom role may hold, sorted: a workspace's admin's.
  - **`custom_kinds`:** the kinds of resource a custom role may be granted on.
  - Every role and kind it lists is one `Catalog.role` accepts.
- **The deployment's roles, an operator's and the application's, aren't in it:** they are granted apart from any tenant, through `/operators` and the application's own configuration.
- **Every surface reads it:** `Grants.catalog()`, and `GET /grantr/v1/catalog`. It is the deployment's, the same in every tenant, so it names none, and any caller may read it. A request with no caller is a 401, as every route's is.
- **It reads the catalog as built, less a role that holds nothing:** an application that hands grantr no reflexr catalog has no `rule` role in it, since that role then holds no action.

## Options considered

| Option | For | Against |
|---|---|---|
| **A catalog read in grantr (chosen)** | The roles and actions grantr checks against; nothing copied | A route to keep |
| grantr's built-in roles and actions copied into admin, with a test that fails if they drift | No grantr change | grantr's model in the browser; the actions depend on the application's catalogs |
| Names typed by hand, with grantr's refusals shown | Nothing copied | A form that can't say what is allowed |
| **One read for the deployment (chosen)** | The catalog is the deployment's | A tenant's custom roles are read apart, from `/roles` |
| A read per tenant, with its custom roles in it | One read for a form | The same catalog in every tenant's answer |

## Consequences

- Easier: portalr's admin offers the roles each resource may be granted, and the actions a custom role may hold, as grantr has them.
- Harder: a change to where a built-in role is granted changes the catalog every UI reads, as it should.
