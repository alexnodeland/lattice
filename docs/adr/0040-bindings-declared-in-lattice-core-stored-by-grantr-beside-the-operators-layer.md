# ADR-0040: Bindings declared in lattice-core, stored by grantr beside the operator's layer

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s O13 and [RFC-0013](../rfcs/0013-event-sources-stored-workflows-and-reflexrs-catalog.md)'s D8; reads [ADR-0018](0018-lattice-core-what-the-libraries-share.md) as [ADR-0032](0032-the-capability-registry-in-lattice-core-four-tiers-three-effects-and-entry-points.md) does

## Context

A binding says which of a source's events reach which workspace. Three packages read bindings: reflexr's intake routes each occurrence by them, relayr's trackers derive their `TrackerBinding` from them, and the code sessions' repositories bind a forge's. None of the three imports another.

RFC-0013 defines the binding and its port, and RFC-0011's O13 puts both in lattice-core, stored by grantr. ADR-0018 moves code into lattice-core only when two packages already have it word for word. Like the capability contracts (ADR-0032), this is a new contract the libraries must agree on, declared once, as integrations (ADR-0027) and settings (ADR-0030) are.

## Decision

- **`lattice_core.bindings`** declares the contract. It imports only the standard library, pydantic and lattice-core's `capabilities` for its JSON types, and needs no extra.
  - **`Binding`**, as RFC-0013 gives it: id (`bnd_` and 16 hex digits), tenant, workspace, source (a spec's name, lowercase and hyphens), connection, `select`, `types`, `trust`, `options`, `bound_at` and `by`.
    - `types=None` receives every type the source has. An empty set is refused, since a binding that receives nothing is a mistake, not a setting.
    - `level(source)` is the level the source's events have through it: the source's, or its `trust` if lower.
  - **`Trust`**, the three levels, lowest first, and `lowest(...)`, since every step of a level only lowers it. They are declared here because the binding names them; reflexr re-exports `Trust` when its envelopes carry it (RFC-0013).
  - **`Bindings`**, the port: `for_connection(source, connection)`, every tenant's bindings of a connection, which the intake routes by; and `for_workspace(tenant, workspace)`.
  - **`FakeBindings`**, in memory, for tests.
  - **`CONTRACT = "1.0.0"`** and its schema, `schemas/bindings.v1.json`, as the other contracts have.
- **grantr stores the tenant's layer** in `grantr_bindings`, with row-level security by tenant, beside the operator's layer from the deployment's configuration, which an admin's read shows read-only. Each change is a grantr command, audited in its transaction, under `grantr:manage_bindings`, which a tenant's owners and admins hold. `for_connection` reads across tenants, as the approvals sweep does, for the deployment's intake alone. That is grantr's next change.

## Options considered

### Option A: In lattice-core, stored by grantr (chosen)

**Pros:** each reader imports one module, and a binding is changed, audited and isolated by tenant where integrations and settings already are.
**Cons:** lattice-core holds a type that only sources use.

### Option B: In reflexr, read by the others through it

**Cons:** relayr and the code sessions would import reflexr, which the libraries' independence forbids.

## Consequences

- Easier: reflexr's intake, relayr's trackers and the code sessions read the same type, and the template's `TRACKER_BINDINGS` becomes the operator's layer of it (RFC-0013).
- Harder: a change to a binding's meaning is a contract change, versioned and checked as the others are.
- reflexr's and relayr's layering tests gain `lattice_core.bindings` as they import it.

## Action items

1. [x] `lattice_core.bindings`, its fake and its schema, tested.
2. [ ] grantr's store, its commands under `grantr:manage_bindings`, and the operator's layer.
3. [ ] reflexr's intake and relayr's trackers reading them (RFC-0013).
