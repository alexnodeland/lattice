# portalr

<p>
  <a href="https://lattice.alexnodeland.com/portalr/"><img alt="Docs" src="https://img.shields.io/badge/docs-lattice.alexnodeland.com%2Fportalr-005A87"></a>
  <a href="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml"><img alt="Nightly" src="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12, 3.13 and 3.14" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-005A87">
  <img alt="Coverage: 100%" src="https://img.shields.io/badge/coverage-100%25-005A87">
  <img alt="Typed: pyright strict" src="https://img.shields.io/badge/typed-pyright%20strict-005A87">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/portalr/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-005A87"></a>
</p>

**portalr** is the planned portal into an application built on the family: an `app` UI for the people who use it, to chat with its agents and see their artifacts, proposals, rules and runs, and an `admin` UI for those who run it, to manage access and see feedback, evaluations, usage and spend. Both will be static single-page apps in React, sharing a typed `client` and a `ui` kit, and served by a router the application mounts beside the libraries'.

> **Status:** planned, not yet usable. Its foundation is done: the package, its decisions and its [v0.1 plan](https://lattice.alexnodeland.com/portalr/rfcs/0001-v0.1-implementation-plan/). The package holds only its version so far, and everything below describes what the plan's phases build. Its mark is drawn in the plan's phase 2.

## Why

Every surface in the family is an API, a WebSocket or an MCP server, so an application built on it has to build its own UI before anyone can use it, and running one is blind without an admin UI. [lattice RFC-0002](https://lattice.alexnodeland.com/rfcs/0002-portalr-the-portal/) designs that UI once, and portalr is where it is built.

## What it will do

- **The browser calls each package's own routes.** A chat goes to artifactr's WebSocket, a rule to reflexr's REST, a grant to grantr's API, on one origin with one token. Nothing proxies them, so nothing re-declares their types ([ADR-0001](https://lattice.alexnodeland.com/portalr/adr/0001-a-router-the-application-mounts/)).
- **Two static apps on Vite, in React 19 and TanStack,** with no server rendering and no Node server ([ADR-0002](https://lattice.alexnodeland.com/portalr/adr/0002-react-and-tanstack-as-two-static-single-page-apps/)).
- **A chat of its own,** thin, in `ui`, over artifactr's protocol ([ADR-0003](https://lattice.alexnodeland.com/portalr/adr/0003-a-chat-of-its-own/)).
- **A tenant's own observability, native,** in the admin UI: its feedback, evaluations, spend, traces and logs, with deep links out to the tools for operators ([ADR-0004](https://lattice.alexnodeland.com/portalr/adr/0004-native-views-of-a-tenants-observability/), [ADR-0005](https://lattice.alexnodeland.com/portalr/adr/0005-operators-see-across-tenants/)).
- **Every read filtered by tenant,** in one module, over the stack's shared stores ([ADR-0006](https://lattice.alexnodeland.com/portalr/adr/0006-shared-stores-every-read-filtered/)).
- **Permissions asked, never guessed.** The UIs ask grantr what the user may do, and the server checks each command again.

## Documentation

portalr's documentation is its section of lattice's site, at **<https://lattice.alexnodeland.com/portalr/>**, built from [`docs/portalr/`](https://github.com/alexnodeland/lattice/tree/main/docs/portalr). Its guides and architecture come with the phases that build what they describe.

- [Architecture decision records](https://lattice.alexnodeland.com/portalr/adr/): why each part will be the way it is.
- [RFCs](https://lattice.alexnodeland.com/portalr/rfcs/): the v0.1 plan, its phases and what each waits on.
- [lattice RFC-0002](https://lattice.alexnodeland.com/rfcs/0002-portalr-the-portal/): the design portalr builds.

## Contributing

See [CONTRIBUTING.md](https://github.com/alexnodeland/lattice/blob/main/CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](https://github.com/alexnodeland/lattice/blob/main/packages/portalr/LICENSE)
