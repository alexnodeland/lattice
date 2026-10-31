# ADR-0032: The capability registry in lattice-core: four tiers, three effects, and entry points

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland
**Records:** [lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s Decisions T1, T6 and, for capabilities, O14, and its reading of [ADR-0018](0018-lattice-core-what-the-libraries-share.md) with [ADR-0027](0027-integrations-switched-per-workspace-through-one-port.md) and [ADR-0030](0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)

## Context

v0.3 would define the tools an agent can call in five places: stored workflows, connectors' actions, the MCP client, code sessions and portr's command catalog ([#940](https://github.com/alexnodeland/lattice/issues/940)). Each would apply tiers, approvals, limits and taint its own way. RFC-0011 puts one registry of capabilities in lattice-core, through which every tool is offered and enforced on one path, and the owner decided its shape on 2026-10-30 and 2026-10-31.

Three things needed settling before the first contract lands:

- **Where it lives.** ADR-0018 moves code into lattice-core "when two or more packages have it word for word", and keeps every package's domain out. A capability contract is new, not moved: no package has it yet. But artifactr, reflexr, grantr and portr must all agree on it, and none may import another.
- **How a tool says what it may do.** artifactr's connected apps vet tools by `Risk`: `read`, `edit`, `code`, `network` and `host`. That mixes what a tool does (`edit`) with what it reaches (`network`), and taint needs the second on its own.
- **How a library's tools reach an application** without the application listing every provider, and without one library importing another.

## Decision

- **The contracts live in lattice-core, read as ADR-0027 and ADR-0030 are.** A contract every library must agree on is declared in lattice-core as types, ports and fakes, and answered elsewhere: each library provides, grantr stores what needs a tenant's store, and the application composes. It is still infrastructure, not a domain: lattice-core holds no store and no provider of its own. Each module imports only the standard library and pydantic, carries its version as `CONTRACT` and publishes a JSON Schema in `packages/lattice-core/schemas/`, named by its major version. The first is `lattice_core.capabilities`, with the `lattice_core.taint` type its `CallContext` carries.
- **Four tiers and three effects (T1).** A capability's tier is `read`, `write`, `run_code` or `outbound`, and decides who may be offered it. Its effects, `reads_private`, `reads_untrusted` and `sends_out`, are what taint reads. One tier, not two. artifactr's `Risk` stays as `artifactr.connect`'s vetting vocabulary and is mapped when it registers: `read` and `edit` are `read` and `write`, `code` is `run_code`, `network` is `outbound` with `sends_out`, and `host` is never registered.
- **Registration through entry points, with explicit composition always allowed (T6).** A library names its provider in its `pyproject.toml`, in the group `lattice.capabilities`, and `lattice_core.capabilities.discover()` loads every one installed with `importlib.metadata`, the standard library, so no dependency is added. An application may pass its providers to `Registry(*providers)` by hand instead, and tests always do. Installing a provider turns nothing on: a capability is offered only where its gate's integration is on (ADR-0027).
- **A call names the client it came through (O14).** `CallContext.via` carries the connection's id, the client's name and the surface (`mcp` or `acp`), or None for a call from lattice's own surfaces, so a provider builds its actor as the client acting for the person, and audit names both.
- **The registry composes and nothing more.** It refuses two capabilities of one name in a scope, lists a scope's capabilities, finds one by name with its provider, and searches by text. It gates and calls nothing: the enforcement path, the only way a capability is called, is its own contract, in the next phase.

## Options considered

| Option | For | Against |
|---|---|---|
| **Contracts in lattice-core (chosen)** | One dependency every library already has; ADR-0027 and ADR-0030 already put ports there | lattice-core grows from shared helpers to the platform's contracts |
| A new `lattice-platform` package | Keeps lattice-core small | Every library would depend on two shared packages |
| The registry in portr | portr reads every catalog anyway | The libraries would need portr to enforce their own tools |
| **Four tiers and three effects (chosen)** | Taint reads effects apart from the tier | artifactr maps its `Risk` once, when it registers |
| `Risk`'s five values everywhere | Nothing to map | Mixes what a tool does with what it reaches |
| **Entry points, and composition by hand (chosen)** | Installing an extra registers its provider; tests stay explicit | Entry points are global to an environment |
| Composition by hand only | No discovery to reason about | Every application lists every provider |

## Consequences

- Easier: a library registers its tools without importing another, and every surface reads one registry.
- Easier: taint reads effects alone, and a tier decides who is offered a tool alone.
- Harder: an extra installed for one application registers for every application in the environment; tests compose by hand.
- Harder: every library takes a higher floor of lattice-core as the contracts land, which changes only by addition and deprecation (ADR-0018).
- Follow-ups, in RFC-0011's phases: the enforcement path and the agents bridge; the approvals, secrets, egress and adapters contracts; schema-level break checks under [#946](https://github.com/alexnodeland/lattice/issues/946); each library's provider.
