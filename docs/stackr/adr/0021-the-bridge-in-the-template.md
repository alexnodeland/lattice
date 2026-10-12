# ADR-0021: The bridge in the template

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds phase 3 of [relayr RFC-0001](../../relayr/rfcs/0001-v0.1-implementation-plan.md), as [stackr RFC-0002](../rfcs/0002-the-combined-system.md#the-template) designs it.

## Context

relayr bridges artifactr and reflexr in one application's process: followers that publish artifactr's events into reflexr, and an outbound adapter through which rules' runs act back in artifactr ([relayr ADR-0001](../../relayr/adr/0001-relayr-its-own-repository-and-package.md)). RFC-0002 has the template's `both` variant wire it in through a `bridge` question, with the incident timeline example (its scenario 3). Followers start from the libraries' `on_open` hook ([relayr ADR-0016](../../relayr/adr/0016-followers-start-on-open.md)). artifactr can list a tenant's workspaces ([artifactr ADR-0058](../../artifactr/adr/0058-a-tenants-workspaces-listed-by-what-each-actor-may-open.md)), and grantr lists the tenants a deployment serves, for its own tools ([grantr ADR-0025](../../grantr/adr/0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md)).

## Decision

- **A `bridge` question, yes by default, asked only with both libraries.** The application then requires `relayr-ai[sql,postgres,otel,langfuse]`, from lattice at the commit it was rendered from, as the libraries are ([ADR-0018](0018-the-template-pins-the-libraries-at-its-own-commit.md)).
- **`bridge.py` is one more part, after the libraries'.** It holds relayr's ledger, in the application's database, its followers and its outbound adapter.
  - Its `watch` is both parts' `on_open`, composed with the feedback mirrors' through `scores.opened`.
  - Its lifespan starts after the parts', so the reactor serves, and stops before them, so each follower lets go of its lease while the libraries are up.
  - At startup it follows every workspace the ledger knows, and, with grantr, every workspace of every tenant: `Grants.served_tenants()`, then artifactr's `Workspaces.list` as relayr's `FOLLOWER`, page by page. If startup fails, the followers it started are closed.
- **reflexr accepts relayr's bridged types,** `BRIDGED`, so the follower never stops on a type it refuses.
- **reflexr reserves the `artifactr` namespace to relayr's source** ([reflexr ADR-0057](../../reflexr/adr/0057-reserved-publishers.md)): `publishers={"artifactr": [SOURCE]}`. Any other client is refused, so no one can forge an author and drive a rule's direct writes.
- **With Langfuse, the parts take relayr's contexts:** `bridged_turns(ledger)` for the runner, `bridged_run` for the reactor, and relayr's contribution to `configure_telemetry`.
- **The example is RFC-0002's incident timeline (`incidents.py`).**
  - An `alert.fired` event fires `open-incident`, whose run creates an incident thread, a `timeline` artifact in it, and a notice.
  - A person's message in the thread fires `timeline-entry`, whose run adds it to the timeline, keyed by its event. It finds the thread's timeline through artifactr's workspaces, as the rule's own actor, `rule_actor(...)`.
  - The two rules' allowlists grant `create_threads` and the `timeline` kind directly; everything else is a proposal or a notice.
- **With grantr, a code rule's actor in artifactr is the application's principal.** `access.py` maps `reflexr:<code rule>`, and a turn acting for it, there, as reflexr's actor for the same run already is.
- **`make smoke-app` sees an event cross each way.** An alert crosses into artifactr as an incident timeline, and the user's message in its thread crosses back onto the timeline.

## Options considered

| Option | For | Against |
|---|---|---|
| **A question, yes by default, with both libraries only (chosen)** | Applications of both libraries get the bridge, and can leave it out | One more variant for the template's checks |
| The bridge always, with both libraries | One variant fewer | An application that keeps its libraries apart carries relayr |
| **A part of its own, last (chosen)** | Its lifespan orders itself around the libraries' by its place | The parts take an `on_open` and a context each |
| Inside `automation.py` | One file fewer | reflexr's part would reach into artifactr's |

## Consequences

- Easier: a new application of both libraries is bridged, and its example shows a rule acting in a thread people work in.
- Harder: the parts' `on_open`, contexts and actions are wired in `create_app`, in an order that matters: the bridge is connected before anything can open a workspace.
