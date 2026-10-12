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

## Why: one model of who may do what

Before grantr, any user of a tenant could do anything in every workspace of that tenant. artifactr's and reflexr's `authorize` hook was asked when a workspace was opened, and never heard what the actor was about to do, so a viewer couldn't be kept from editing. A user had exactly one tenant, set in their token. Nothing stored members, groups or roles, and an integration's key was a person's token.

[lattice RFC-0001](../rfcs/0001-grantr-identity-and-access.md) designs access once, for every surface, and grantr is where its model is built. It imports neither library, and neither imports it: actions cross as strings, and stackr's template wires the two together.

## What it does

- **Check every command and read.** The libraries' hook hears the action, such as `artifactr:edit_artifact`, and asks grantr before each command and read, on REST, WebSocket, MCP and in process ([ADR-0001](adr/0001-the-hook-hears-the-action.md)).
- **Grant down to threads and artifacts.** A role is granted on the deployment, a tenant, a workspace, or a thread, artifact or rule in it; a restricted thread or artifact is hidden from everyone without a role on it ([ADR-0002](adr/0002-grants-down-to-threads-and-artifacts.md), [ADR-0003](adr/0003-visible-to-the-workspace-unless-restricted.md)).
- **Act for a user.** An agent's turn is checked as the person whose message started it ([ADR-0004](adr/0004-an-agent-turn-acts-for-its-user.md)).
- **Own membership.** A user's tenants come from grantr, and each request names its tenant ([ADR-0005](adr/0005-a-users-tenants-from-grantrs-memberships.md)).
- **Built-in and custom roles, groups and service principals,** with keys shown once, and checks that deny by default ([ADR-0006](adr/0006-what-v0-1-includes.md)).
- **An append-only audit log** of every change to access ([ADR-0007](adr/0007-an-append-only-audit-log.md)).
- **Its own model, with OpenFGA-shaped ports,** in memory or in SQL ([ADR-0008](adr/0008-grantrs-own-model-with-openfga-shaped-ports.md)).
- **A deployment-wide `operator` role,** an audited grant held by few ([ADR-0009](adr/0009-a-deployment-wide-operator-role.md)).
- **Keys that can't pass for the libraries' own actors,** since a service principal's id can't take theirs ([ADR-0028](adr/0028-a-principals-id-cant-pass-for-the-libraries-actors.md)).
- **Row-level security under the libraries' scoping,** with PostgreSQL keeping each tenant's rows to that tenant ([ADR-0026](adr/0026-row-level-security-under-the-scoping.md)).

stackr's template wires it in by default. [RFC-0001](rfcs/0001-v0.1-implementation-plan.md#phases) built it in seven phases after the foundation.

## Where to go next

| If you want to | Read |
|---|---|
| Set it up, and ask it from the libraries | [Getting started](getting-started.md) |
| Choose roles, define your own, and review who may do what | [Roles and grants](guides/roles-and-grants.md), and the [permission matrix](guides/matrix.md) |
| Keep a thread or artifact to some of a workspace's members | [Restricted threads and artifacts](guides/restricted-items.md) |
| Give an integration a key | [Service principals and keys](guides/keys.md) |
| Have PostgreSQL keep tenants apart under grantr | [Row-level security](guides/row-level-security.md) |
| See how it is built | The [architecture](architecture.md), and the [reference](reference.md) |
| Understand why each part is the way it is | The [decision records](adr/README.md) |
| See the plan, its phases and what each waits on | [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and the [RFCs](rfcs/README.md) |
| Read the design grantr builds | [lattice RFC-0001](../rfcs/0001-grantr-identity-and-access.md) |
| Use the mark and its colours | The [brand page](assets/brand/README.md) |
| See what has changed | The [changelog](project/changelog.md) |
| Contribute | [Contributing](../project/contributing.md) |
