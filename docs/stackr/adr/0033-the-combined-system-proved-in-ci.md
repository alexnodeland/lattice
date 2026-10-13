# ADR-0033: The combined system, proved in CI

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [RFC-0002](../rfcs/0002-the-combined-system.md)'s phase 7, and [relayr RFC-0001](../../relayr/rfcs/0001-v0.1-implementation-plan.md)'s: the product repository, and the exit criterion

## Context

RFC-0002's phase 7 ends when "the product repository passes its CI on the stack": a repository generated from the template, holding the combined system as a product, as [artifactr ADR-0032](../../artifactr/adr/0032-libraries-and-the-stackr-template.md) says. Phases 1 to 6 built everything that repository would hold, in relayr and in the template.

lattice's CI already generates that application, with both libraries, evals, grantr and the bridge, on every change to stackr or a library. Two of its jobs check it:

- **Template** generates it at the commit under test, and runs its own CI, `make check`, through `scripts/check-app`.
- **Smoke**, in its two rows with an application, "everything on local Supabase, and an application" and "a single host, behind Caddy, and an application", builds it, runs it on the stack, and checks it end to end with `make smoke-app`.

## Decision

- **There is no separate product repository for v0.1.** Phase 7's exit criterion becomes: the application generated from the template passes its own CI, and runs end to end on the stack. The Template and Smoke jobs meet it together. On the stack, `make smoke-app` checks:
  - sign-in and tenants;
  - both agents' traces in Tempo and Langfuse;
  - an alert opening an incident thread with its timeline, and a person's message there joining it;
  - the incident's resolution posting a closing notice and proposing its postmortem;
  - a rule drafted in a thread going live once a person accepts it, while a forged acceptance is refused.
- **A real product repository comes with the user's own product,** generated from the template when there is a product to build, not as a placeholder.

## Options considered

| Option | For | Against |
|---|---|---|
| **The Template and Smoke jobs as the proof (chosen)** | Checked on every change, at the commit under test, with nothing to keep in step | No repository a product team could fork as it is |
| A product repository generated now | A standing example of the combined system | A second repository to keep in step with the template, with its own CI and secrets, holding no product |
| An example under lattice's `examples/` | A generated application to read, beside the code it uses | Generated code checked in, which drifts from the template unless CI regenerates and compares it, while the Template job already generates it |

## Consequences

- Easier: the combined system is proved on every change to stackr or a library, and can't drift from the template.
- Harder: someone starting a product generates it themselves, with `copier copy`, as the [combined system guide](../guides/combined-system.md) shows.
- Revisit: a product repository once a product needs one.
