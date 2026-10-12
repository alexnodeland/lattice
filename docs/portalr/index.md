---
title: portalr
description: The planned portal into an application built on the family, with an app UI to chat with its agents and see their work, and an admin UI to manage access and see feedback, evaluations, usage and spend.
hide:
  - navigation
---

<div class="portalr-hero" markdown>

<h1 class="portalr-visually-hidden">portalr</h1>

![portalr](assets/brand/lockup-light.svg#gh-light-mode-only)
![portalr](assets/brand/lockup-dark.svg#gh-dark-mode-only)

The planned portal into an application built on the family: an `app` UI for the people who use it, to chat with its agents and see their artifacts, proposals, rules and runs, and an `admin` UI for those who run it, to manage access and see feedback, evaluations, usage and spend.

</div>

!!! note "In progress, not yet usable"

    Built so far: its decisions and [v0.1 plan](rfcs/0001-v0.1-implementation-plan.md), the Bun workspace, its brand with `ui`'s tokens and first primitives, the typed `client`, and the router with its readers, tested against the stack's tools for two tenants, as its [architecture](architecture.md) describes. The two UIs come with the plan's later phases.

## Why: the family has no face

Every surface in the family is an API, a WebSocket or an MCP server, so an application built on it has to build its own UI before anyone can use it. Running one is blind without an admin UI: granting access, reviewing proposals, seeing what users thought of the agent and what each tenant spends all need one, and grantr's model is only usable through one.

[lattice RFC-0002](../rfcs/0002-portalr-the-portal.md) designs that UI once, and portalr is where it is built.

## What it will do

- **The browser calls each package's own routes.** A chat goes to artifactr's WebSocket, a rule to reflexr's REST, a grant to grantr's API, on one origin with one token. portalr's router serves the UIs and adds only what no package has ([ADR-0001](adr/0001-a-router-the-application-mounts.md)).
- **Two static apps on Vite, in React 19 and TanStack,** sharing a typed `client`, whose types are generated from each package's committed documents, and a `ui` kit ([ADR-0002](adr/0002-react-and-tanstack-as-two-static-single-page-apps.md)).
- **A chat of its own,** thin, over artifactr's protocol ([ADR-0003](adr/0003-a-chat-of-its-own.md)).
- **A tenant's own observability,** in the admin UI: its feedback, evaluations, usage and spend, traces and logs, with deep links out to the tools for operators ([ADR-0004](adr/0004-native-views-of-a-tenants-observability.md), [ADR-0005](adr/0005-operators-see-across-tenants.md)).
- **Every read filtered by tenant,** in one module, over the stack's shared stores ([ADR-0006](adr/0006-shared-stores-every-read-filtered.md)).
- **Permissions asked, never guessed.** The UIs ask grantr what the user may do, and the server checks each command again.

[RFC-0001](rfcs/0001-v0.1-implementation-plan.md#phases) builds these in eight phases after the foundation, and says what each waits on in grantr and the other packages. Its guides and reference come with the phases that build what they describe.

## Where to go next

| If you want to | Read |
|---|---|
| See how it is built | The [architecture](architecture.md) |
| Understand why each part will be the way it is | The [decision records](adr/README.md) |
| See the plan, its phases and what each waits on | [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and the [RFCs](rfcs/README.md) |
| Read the design portalr builds | [lattice RFC-0002](../rfcs/0002-portalr-the-portal.md) |
| Use the marks and their colours | The [brand page](assets/brand/README.md) |
| See what has changed | The [changelog](project/changelog.md) |
| Contribute | [Contributing](../project/contributing.md) |
