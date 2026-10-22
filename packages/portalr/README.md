<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/portalr/assets/brand/banner-dark.svg">
  <img alt="portalr: the portal into an application built on lattice." src="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/portalr/assets/brand/banner-light.svg" width="100%">
</picture>

<p>
  <a href="https://lattice.alexnodeland.com/portalr/"><img alt="Docs" src="https://img.shields.io/badge/docs-lattice.alexnodeland.com%2Fportalr-6B2FA0"></a>
  <a href="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml"><img alt="Nightly" src="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12, 3.13 and 3.14" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-6B2FA0">
  <img alt="Coverage: 100%" src="https://img.shields.io/badge/coverage-100%25-6B2FA0">
  <img alt="Typed: pyright strict" src="https://img.shields.io/badge/typed-pyright%20strict-6B2FA0">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/portalr/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-6B2FA0"></a>
</p>

**portalr** is the portal into an application built on lattice: an `app` UI for the people who use it, to chat with its agents and see their artifacts, proposals, rules and runs, and an `admin` UI for those who run it, to manage access and see feedback, evaluations, usage and spend. Both are static single-page apps in React, sharing a typed `client` and a `ui` kit, and served by a router the application mounts beside the libraries'.

> **Status:** built, and on PyPI. The router, the app's areas and the admin UI, including the operators' tenants and tools and people shown by email, are built and tested, and stackr's template mounts it ([guides](https://lattice.alexnodeland.com/portalr/getting-started/), [architecture](https://lattice.alexnodeland.com/portalr/architecture/)). Not built yet: magic links and other sign-in providers. Its wheel carries both UIs: `uv add portalr`.

## Why

Every surface in lattice is an API, a WebSocket or an MCP server, so an application built on it has to build its own UI before anyone can use it, and running one is blind without an admin UI. [lattice RFC-0002](https://lattice.alexnodeland.com/rfcs/0002-portalr-the-portal/) designs that UI once, and portalr is where it is built.

## What it does

- **The browser calls each package's own routes.** A chat goes to artifactr's WebSocket, a rule to reflexr's REST, a grant to grantr's API, on one origin with one token. Nothing proxies them, so nothing re-declares their types ([ADR-0001](https://lattice.alexnodeland.com/portalr/adr/0001-a-router-the-application-mounts/)).
- **Two static apps on Vite, in React 19 and TanStack,** with no server rendering and no Node server ([ADR-0002](https://lattice.alexnodeland.com/portalr/adr/0002-react-and-tanstack-as-two-static-single-page-apps/)).
- **A chat of its own,** thin, in `ui`, over artifactr's protocol ([ADR-0003](https://lattice.alexnodeland.com/portalr/adr/0003-a-chat-of-its-own/)).
- **A tenant's own observability, native,** in the admin UI: its feedback, evaluations, spend, traces and logs, with deep links out to the tools for operators ([ADR-0004](https://lattice.alexnodeland.com/portalr/adr/0004-native-views-of-a-tenants-observability/), [ADR-0005](https://lattice.alexnodeland.com/portalr/adr/0005-operators-see-across-tenants/)).
- **Every read filtered by tenant,** in one module, over the stack's shared stores ([ADR-0006](https://lattice.alexnodeland.com/portalr/adr/0006-shared-stores-every-read-filtered/)).
- **Permissions asked, never guessed.** The UIs ask grantr what the user may do, and the server checks each command again.
- **Native files, uploads and check-out.** A person uploads a file, reads its pages and words, and checks it out into its app's browser build, framed on an origin of its own ([ADR-0049](https://lattice.alexnodeland.com/portalr/adr/0049-checking-a-native-file-out-and-in/)).
- **Forms, dashboards and mini apps in the chat.** A mini app runs in a sandbox on an origin of its own, inline in its thread, with a full view ([ADR-0051](https://lattice.alexnodeland.com/portalr/adr/0051-mini-apps-the-sandboxed-frame-and-its-bridge/), [ADR-0052](https://lattice.alexnodeland.com/portalr/adr/0052-artifacts-inline-in-their-thread/)).
- **Connected apps' calls approved.** An agent's call that runs code in an operator's own FreeCAD or Blender waits on a card that shows what it would run.
- **Brand kits.** A deployment's kit sets its colours, type, marks and words; `portalr brand init` starts one and `portalr brand validate` checks it ([white-labelling](https://lattice.alexnodeland.com/portalr/guides/white-labelling/)).
- **A new version, offered.** A tab that outlived a deploy says a new version is ready, and reloads only when the person chooses ([ADR-0058](https://lattice.alexnodeland.com/portalr/adr/0058-a-new-version-offered-to-a-stale-tab/)).

## Documentation

portalr's documentation is its section of lattice's site, at **<https://lattice.alexnodeland.com/portalr/>**, built from [`docs/portalr/`](https://github.com/alexnodeland/lattice/tree/main/docs/portalr).

- [Getting started](https://lattice.alexnodeland.com/portalr/getting-started/): install the wheel, mount the router, sign in.
- [Guides](https://lattice.alexnodeland.com/portalr/guides/app/): the app, the admin UI, an operator's runbook, and what portalr keeps from view.
- [Architecture decision records](https://lattice.alexnodeland.com/portalr/adr/): why each part is the way it is.
- [RFCs](https://lattice.alexnodeland.com/portalr/rfcs/): the v0.1 plan, its phases and what each waits on.
- [lattice RFC-0002](https://lattice.alexnodeland.com/rfcs/0002-portalr-the-portal/): the design portalr builds.
- [Brand](https://lattice.alexnodeland.com/portalr/assets/brand/): the marks and their colours.

## Contributing

See [CONTRIBUTING.md](https://github.com/alexnodeland/lattice/blob/main/CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](https://github.com/alexnodeland/lattice/blob/main/packages/portalr/LICENSE). The UIs carry lattice's typefaces, Schibsted Grotesk and Fragment Mono, under the [SIL Open Font License 1.1](https://github.com/alexnodeland/lattice/tree/main/packages/portalr/web/ui/src/fonts).
