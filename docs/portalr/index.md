---
title: portalr
description: The portal into an application built on lattice, with an app UI to chat with its agents and see their work, and an admin UI to manage access and see feedback, evaluations, usage and spend.
hide:
  - navigation
---

<div class="portalr-hero" markdown>

<h1 class="portalr-visually-hidden">portalr</h1>

![portalr](assets/brand/lockup-light.svg#gh-light-mode-only)
![portalr](assets/brand/lockup-dark.svg#gh-dark-mode-only)

The portal into an application built on lattice: an `app` UI for the people who use it, to chat with its agents and see their artifacts, proposals, rules and runs, and an `admin` UI for those who run it, to manage access and see feedback, evaluations, usage and spend.

</div>

!!! note "Built, and not yet released"

    Built and tested: the router and its readers, the app's areas (threads and chat, artifacts, proposals, runs, rules, restricting and sharing a thread), the admin UI (home, access, audit, feedback, usage, traces, logs and health, runs, and the operators' tenants, deployment audit and tools), people shown by email, and the `portal` question of [stackr's template](../stackr/guides/template.md), which mounts it in a generated application. Each area has a scenario in a browser against a test application. The [guides](getting-started.md) describe what is built, and [the architecture](architecture.md) how.

    Not built yet: the UIs' scenarios against a generated application and the Acceptance job's portalr steps (phase 7b of the [plan](rfcs/0001-v0.1-implementation-plan.md)); the template naming people by email; magic links and other sign-in providers. It is not on PyPI: install its wheel ([Getting started](getting-started.md#install)).

## Why: lattice has no face

Every surface in lattice is an API, a WebSocket or an MCP server, so an application built on it has to build its own UI before anyone can use it. Running one is blind without an admin UI: granting access, reviewing proposals, seeing what users thought of the agent and what each tenant spends all need one, and grantr's model is only usable through one.

[lattice RFC-0002](../rfcs/0002-portalr-the-portal.md) designs that UI once, and portalr is where it is built.

## What it does

- **The browser calls each package's own routes.** A chat goes to artifactr's WebSocket, a rule to reflexr's REST, a grant to grantr's API, on one origin with one token. portalr's router serves the UIs and adds only what no package has ([ADR-0001](adr/0001-a-router-the-application-mounts.md)).
- **Two static apps on Vite, in React 19 and TanStack,** sharing a typed `client`, whose types are generated from each package's committed documents, and a `ui` kit ([ADR-0002](adr/0002-react-and-tanstack-as-two-static-single-page-apps.md)).
- **A chat of its own,** thin, over artifactr's protocol ([ADR-0003](adr/0003-a-chat-of-its-own.md)).
- **A tenant's own observability,** in the admin UI: its feedback, evaluations, usage and spend, traces and logs, with deep links out to the tools for operators ([ADR-0004](adr/0004-native-views-of-a-tenants-observability.md), [ADR-0005](adr/0005-operators-see-across-tenants.md)).
- **Every read filtered by tenant,** in one module, over the stack's shared stores ([ADR-0006](adr/0006-shared-stores-every-read-filtered.md)).
- **Permissions asked, never guessed.** The UIs ask grantr what the user may do, and the server checks each command again.

[RFC-0001](rfcs/0001-v0.1-implementation-plan.md#phases) builds these in eight phases after the foundation, and says what each waited on in grantr and the other packages. Phases 1 to 6 and 8 are done. Of phase 7, the template's portal is done, and the scenarios against a generated application and the acceptance steps are not.

## Where to go next

| If you want to | Read |
|---|---|
| Mount it and sign in | [Getting started](getting-started.md) |
| Use the app | [The app](guides/app.md) |
| Run a tenant | [The admin UI](guides/admin.md) |
| Run the deployment | [An operator's runbook](guides/operators.md) |
| Know what is withheld and why | [What portalr keeps from view](guides/privacy.md) |
| See how it is built | The [architecture](architecture.md) |
| Understand why each part is the way it is | The [decision records](adr/README.md) |
| See the plan, its phases and what each waits on | [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and the [RFCs](rfcs/README.md) |
| Read the design portalr builds | [lattice RFC-0002](../rfcs/0002-portalr-the-portal.md) |
| Use the marks and their colours | The [brand page](assets/brand/README.md) |
| See what has changed | The [changelog](project/changelog.md) |
| Contribute | [Contributing](../project/contributing.md) |
