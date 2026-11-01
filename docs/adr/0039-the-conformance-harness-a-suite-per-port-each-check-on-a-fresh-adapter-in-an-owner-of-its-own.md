# ADR-0039: The conformance harness: a suite per port, each check on a fresh adapter, in an owner of its own

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s "one conformance harness" (#944), phase 5's first part; beside [ADR-0032](0032-the-capability-registry-in-lattice-core-four-tiers-three-effects-and-entry-points.md)

## Context

RFC-0011 decides that every port has an in-memory fake and one contract suite, run against the fake and against each adapter, both in the adapter's own CI under pytest and from `make validate` against a running deployment. It says what the harness is, "plain async checks that take a factory and return results", and that each suite checks the adapter's `implements` against the port's version. `lattice_core.adapters` already declares the spec, discovery and `require`, and the secrets port has its fake. What the RFC leaves open:

- what a check is given;
- what a run returns;
- how a suite runs against a store a deployment is using;
- where pytest comes in.

## Decision

- **`lattice_core.conformance`** holds the harness, importing only the standard library, pydantic and lattice-core, so `make validate` runs it without pytest:
  - A `Check` is a name, a sentence of what the contract says, and an async function given the adapter, which raises where the adapter breaks the contract (`Failed`, with `expect` and `refuses` to say how).
  - A `Suite` is a port's name and contract version, the kind of adapter that answers it, how to take what the factory built as the port, and its checks, named apart.
- **Each check is given an adapter of its own,** built by the adapter's factory from its configuration, so no check depends on another's leftovers or order.
- **`run(suite, spec, config)` returns a `Report`,** and never raises for what an adapter does:
  - Its first result is whether the adapter is of the suite's kind and implements the port's version. If not, nothing more runs, as RFC-0011's "the harness refuses one that doesn't match".
  - Then each check's result follows, passed or failed with what was raised. A check that outlives its limit (30 seconds by default) fails.
  - The report is pydantic, so `make validate` prints it and admin's Adapters view can show it.
  - `checks=` runs some checks by name.
- **A check works within an owner of its own:** the secrets suite puts every secret in tenants named `conformance-` and a random token, and deletes them as the check ends, pass or fail. So it runs against a deployment's store in use and leaves it as it was.
- **`lattice_core.conformance.secrets.SECRETS`** is the secrets port's suite, nine checks:
  - a value read back within its owner and for its purpose;
  - a reader outside its owner, or for another purpose, refused;
  - a reference naming another owner reading nothing;
  - a rotation's grace kept, and ended;
  - a revocation ending every version;
  - a listing within its owner, holding no value;
  - deleting what an owner holds deleting it alone;
  - a reference to no secret unknown.
- **The pytest plugin is `lattice_core.conformance.plugin`,** behind a new `conformance` extra (pytest):
  - `conformance_test(suite, spec, config)` returns a test with a case per check, which an adapter's test module assigns to a name pytest collects.
  - Each case runs its check in an event loop of its own, so it needs no async plugin.
- **The harness's own tests** run the fake through the suite, and a store that breaks each rule, which must fail that rule's check (RFC-0011's "a fake adapter that passes and one that fails each check").

## Options considered

### Option A: Plain async checks, an adapter each, a report (chosen)

**Pros:** the same suite runs under pytest and from a command, against a fake or a live store; a report says every failure, not the first.
**Cons:** a check can't share an expensive setup with the next; each builds its adapter, which for a database store is a connection each.

### Option B: pytest tests the adapter's CI imports

**Cons:** `make validate` would need pytest in the deployment's image, and its results would be pytest's output, not a report admin can show.

### Option C: One adapter for the whole suite

**Cons:** a check that fails midway leaves what it put for the next one, so one break reads as several, and order matters.

## Consequences

- Easier: an adapter's CI runs its port's suite in one line, and a new port's suite is a tuple of checks.
- Harder: a check must clean up after itself on a live store, and use only owners it makes up. A suite whose port can't be cleaned up after has to say how it runs against a deployment.
- `make validate`, the application's command that runs each configured adapter through its suite against the deployment, is its own change, with the configuration that names each port's adapter.
- Supabase Vault's adapter runs the secrets suite in its CI when it comes (#942).

## Action items

1. [x] The harness, the secrets suite and the pytest plugin, tested against the fake and a store breaking each rule.
2. [ ] `make validate` in the application template, running each configured adapter through its suite.
3. [ ] Supabase Vault's adapter passing the secrets suite (#942).
