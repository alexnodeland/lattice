---
title: grantr
description: The identity and access package for artifactr and reflexr, which decides what each actor may do in a tenant before every command and read.
hide:
  - navigation
---

<div class="grantr-hero" markdown>

<h1 class="grantr-visually-hidden">grantr</h1>

![grantr](assets/brand/lockup-light.svg#gh-light-mode-only)
![grantr](assets/brand/lockup-dark.svg#gh-dark-mode-only)

Identity and access for the family: tenants, their members, groups, roles and service principals, and the grants that bind them to tenants, workspaces, threads, artifacts and rules.

</div>

!!! note "In progress"

    grantr's core, storage and admin API are built: its model, built-in and custom roles, groups, service principals and keys, checks, the libraries' hooks, the audit log, in-memory and SQL storage, the admin router and telemetry, as its [architecture](architecture.md) describes. stackr's template wires it in by default: each library asks it before every command and read. It restricts threads and artifacts and says who sees them; artifactr's filtering by it, and row-level security, come next; the rest of this page describes what the [v0.1 plan](rfcs/0001-v0.1-implementation-plan.md)'s phases build.

## Why: one model of who may do what

Today, any user of a tenant may do anything in every workspace of that tenant. artifactr's and reflexr's `authorize` hook is asked when a workspace is opened, and never hears what the actor is about to do, so a viewer can't be kept from editing. A user has exactly one tenant, set in their token. Nothing stores members, groups or roles, and an integration's key is a person's token.

[lattice RFC-0001](../rfcs/0001-grantr-identity-and-access.md) designs access once, for every surface, and grantr is where its model is built. It imports neither library, and neither imports it: actions cross as strings, and stackr's template wires the two together.

## What it will do

- **Check every command and read.** The libraries' widened hook hears the action, such as `artifactr:edit_artifact`, and asks grantr before each command and read, on REST, WebSocket, MCP and in process ([ADR-0001](adr/0001-the-hook-hears-the-action.md)).
- **Grant down to threads and artifacts.** A role is granted on the deployment, a tenant, a workspace, or a thread, artifact or rule in it; a restricted thread or artifact is hidden from everyone without a role on it ([ADR-0002](adr/0002-grants-down-to-threads-and-artifacts.md), [ADR-0003](adr/0003-visible-to-the-workspace-unless-restricted.md)).
- **Act for a user.** An agent's turn is checked as the person whose message started it ([ADR-0004](adr/0004-an-agent-turn-acts-for-its-user.md)).
- **Own membership.** A user's tenants come from grantr, and each request names its tenant ([ADR-0005](adr/0005-a-users-tenants-from-grantrs-memberships.md)).
- **Built-in and custom roles, groups and service principals,** with keys shown once, and checks that deny by default ([ADR-0006](adr/0006-what-v0-1-includes.md)).
- **An append-only audit log** of every change to access ([ADR-0007](adr/0007-an-append-only-audit-log.md)).
- **Its own model, with OpenFGA-shaped ports,** in memory or in SQL ([ADR-0008](adr/0008-grantrs-own-model-with-openfga-shaped-ports.md)).
- **A deployment-wide `operator` role,** an audited grant held by few ([ADR-0009](adr/0009-a-deployment-wide-operator-role.md)).

[RFC-0001](rfcs/0001-v0.1-implementation-plan.md#phases) builds these in seven phases after the foundation, and says where each lands. Its guides come with the phases that wire it in.

## Where to go next

| If you want to | Read |
|---|---|
| See how it is built | The [architecture](architecture.md), and the [reference](reference.md) |
| Understand why each part is the way it is | The [decision records](adr/README.md) |
| See the plan, its phases and what each waits on | [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and the [RFCs](rfcs/README.md) |
| Read the design grantr builds | [lattice RFC-0001](../rfcs/0001-grantr-identity-and-access.md) |
| Use the mark and its colours | The [brand page](assets/brand/README.md) |
| See what has changed | The [changelog](project/changelog.md) |
| Contribute | [Contributing](../project/contributing.md) |
