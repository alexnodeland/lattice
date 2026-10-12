<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/grantr/assets/brand/banner-dark.svg">
  <img alt="grantr: identity and access for artifactr and reflexr." src="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/grantr/assets/brand/banner-light.svg" width="100%">
</picture>

<p>
  <a href="https://lattice.alexnodeland.com/grantr/"><img alt="Docs" src="https://img.shields.io/badge/docs-lattice.alexnodeland.com%2Fgrantr-6B5300"></a>
  <a href="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml"><img alt="Nightly" src="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12, 3.13 and 3.14" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-6B5300">
  <img alt="Coverage: 100%" src="https://img.shields.io/badge/coverage-100%25-6B5300">
  <img alt="Typed: pyright strict" src="https://img.shields.io/badge/typed-pyright%20strict-6B5300">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/grantr/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-6B5300"></a>
</p>

**grantr** is the identity and access package for [artifactr](https://lattice.alexnodeland.com/artifactr/) and [reflexr](https://lattice.alexnodeland.com/reflexr/): tenants, their members, groups, roles and service principals, and the grants that bind them to tenants, workspaces, threads, artifacts and rules. The libraries ask it, through their own hooks, before every command and read. It imports neither library, and neither imports it.

> **Status:** v0.1's scope is built: the model, built-in and custom roles, groups, service principals and keys, checks, the libraries' hooks, restricted threads and artifacts, the audit log, in-memory and SQL storage with row-level security (the `sql`, `sqlite` and `postgres` extras), the admin router (the `fastapi` extra) and telemetry. stackr's template wires it in by default, so each library asks it before every command and read.

## Why

Before grantr, any user of a tenant could do anything in every workspace of that tenant. The libraries' `authorize` hook was asked when a workspace was opened, and never heard what the actor was about to do, so a viewer couldn't be kept from editing. A user had exactly one tenant, set in their token, and nothing stored members, groups or roles. [lattice RFC-0001](https://lattice.alexnodeland.com/rfcs/0001-grantr-identity-and-access/) designs access once, for every surface, and grantr is where its model is built.

## What it does

- **Check every command and read.** The libraries' hook hears the action, such as `artifactr:edit_artifact`, and asks grantr before each command and read, on every surface ([ADR-0001](https://lattice.alexnodeland.com/grantr/adr/0001-the-hook-hears-the-action/)).
- **Grant down to threads and artifacts,** and hide a restricted one from everyone without a role on it ([ADR-0002](https://lattice.alexnodeland.com/grantr/adr/0002-grants-down-to-threads-and-artifacts/), [ADR-0003](https://lattice.alexnodeland.com/grantr/adr/0003-visible-to-the-workspace-unless-restricted/)).
- **Act for a user.** An agent's turn is checked as the person whose message started it ([ADR-0004](https://lattice.alexnodeland.com/grantr/adr/0004-an-agent-turn-acts-for-its-user/)).
- **Own membership.** A user's tenants come from grantr, and each request names its tenant ([ADR-0005](https://lattice.alexnodeland.com/grantr/adr/0005-a-users-tenants-from-grantrs-memberships/)).
- **Built-in and custom roles, groups and service principals,** with keys shown once, and checks that deny by default ([ADR-0006](https://lattice.alexnodeland.com/grantr/adr/0006-what-v0-1-includes/)).
- **An append-only audit log** of every change to access ([ADR-0007](https://lattice.alexnodeland.com/grantr/adr/0007-an-append-only-audit-log/)).
- **Its own model, with OpenFGA-shaped ports,** in memory or in SQL ([ADR-0008](https://lattice.alexnodeland.com/grantr/adr/0008-grantrs-own-model-with-openfga-shaped-ports/)), and a deployment-wide `operator` role ([ADR-0009](https://lattice.alexnodeland.com/grantr/adr/0009-a-deployment-wide-operator-role/)).
- **Row-level security under the libraries' scoping,** with PostgreSQL keeping each tenant's rows to that tenant ([ADR-0026](https://lattice.alexnodeland.com/grantr/adr/0026-row-level-security-under-the-scoping/)).

## Quick start

```python
from artifactr.workspace import ACTIONS as ARTIFACTR
from grantr import Grants, InMemoryStorage, Resource, User

grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR])
await grants.first_operator("root")
await grants.create_tenant("acme", owner="alice", by=User(id="root"))
await grants.add_member("acme", User(id="bob"), by=User(id="alice"))
main = Resource(kind="workspace", workspace="main")
await grants.grant("acme", "editor", on=main, to=User(id="bob"), by=User(id="alice"))
assert await grants.check("acme", User(id="bob"), "artifactr:edit_artifact", main)
```

[Getting started](https://lattice.alexnodeland.com/grantr/getting-started/) goes on to the libraries' hooks, SQL storage and the admin API.

## Documentation

grantr's documentation is its section of lattice's site, at **<https://lattice.alexnodeland.com/grantr/>**, built from [`docs/grantr/`](https://github.com/alexnodeland/lattice/tree/main/docs/grantr).

- [Getting started](https://lattice.alexnodeland.com/grantr/getting-started/), and the guides: roles and grants, restricted threads and artifacts, service principals and keys, row-level security, and the permission matrix.
- [Architecture](https://lattice.alexnodeland.com/grantr/architecture/): the model, the checks, the commands and the storage port.
- [Architecture decision records](https://lattice.alexnodeland.com/grantr/adr/): why each part is the way it is.
- [RFCs](https://lattice.alexnodeland.com/grantr/rfcs/): the v0.1 plan, its phases and what each waits on.
- [Identity and access](https://lattice.alexnodeland.com/rfcs/0001-grantr-identity-and-access/), lattice's RFC-0001: the design grantr builds.
- [Brand](https://lattice.alexnodeland.com/grantr/assets/brand/): the mark and its colours.

## Contributing

See [CONTRIBUTING.md](https://github.com/alexnodeland/lattice/blob/main/CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](https://github.com/alexnodeland/lattice/blob/main/packages/grantr/LICENSE)
