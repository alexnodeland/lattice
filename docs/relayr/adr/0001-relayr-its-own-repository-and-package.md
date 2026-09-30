# ADR-0001: relayr, its own repository and package

**Status:** Accepted; partly superseded by [ADR-0013](0013-relayr-in-lattice.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Records decision D1 of [stackr RFC-0002][rfc-0002], the combined system.

## Context

artifactr and reflexr are independent siblings: neither imports the other, and the adapters between them belong to the system that combines them ([reflexr ADR-0003][r-adr-0003]). That system is an application built from stackr's template ([artifactr ADR-0032][a-adr-0032]). The adapters carry invariants that are easy to get wrong: ids derived for idempotency, loop control, and allowlists that are the only check on some commands. Every application that wrote its own would meet the same hard parts.

## Decision

- **The bridge is a new sibling repository and package, relayr**, depending on artifactr and reflexr through their public APIs only.
- **It holds** the two adapters, the bridged event types, and the ledger with its in-memory and SQL adapters; later, the `rule` artifact type and the install rule, the proposal-outcome evaluator, and the telemetry links and tags.
- **stackr's template wires it in** through a `bridge` question in its `both` variant, pinned by revision like the libraries.
- **The name is relayr**: it relays events and commands between the two libraries, and fits the family's names. `bridgr` and `linkr` were considered; "link" already means trace and span links in this design.

## Options considered

| Option | For | Against |
|---|---|---|
| **A new sibling repository and package (chosen)** | Its own tests, releases and pinned revision, like the libraries. Any application from the template can use it | One more repository to maintain |
| A package inside stackr | One fewer repository | stackr becomes a library host, and its releases get tied to the stack's |
| Generated code in the template only | Nothing to release | Every application owns a copy of the invariants, and `copier update` has to merge fixes into code that has drifted |
| Only in the product repository | Fastest start | Other applications can't reuse it, and the template can't generate it |
| An extra in one library | No new package | Ruled out by reflexr ADR-0003: neither library imports the other |

## Consequences

- Easier: the invariants are written, tested and fixed once, and the libraries stay independent.
- Harder: one more package to release and pin, and relayr moves with both libraries' public APIs.

[a-adr-0032]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0032-libraries-and-the-stackr-template.md
[r-adr-0003]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0003-independent-sibling-of-artifactr.md
[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md#d1-where-the-bridge-lives-and-its-name
