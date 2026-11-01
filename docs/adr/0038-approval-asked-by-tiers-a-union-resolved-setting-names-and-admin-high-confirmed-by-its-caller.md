# ADR-0038: Approval asked by the tiers a union-resolved setting names, and admin_high confirmed by its caller

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s O5 and O15; amends [ADR-0030](0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md); beside [ADR-0035](0035-one-approval-per-call-bound-to-its-arguments-declared-in-lattice-core-and-stored-by-grantr.md) and [ADR-0037](0037-the-enforcement-path-in-lattice-core-refusals-by-step-approvals-resumed-by-id.md)

## Context

The enforcer asks an `ApprovalPolicy` who must approve each call (ADR-0037), but lattice had no policy. RFC-0011 decided two things for it:

- **O5:** whether a call needs a person depends on its tier. The operator sets the floor, and a tenant or workspace may ask approval on more tiers, never on fewer.
- **O15:** an `admin_high` capability asks the caller's own fresh confirmation on portalr's confirm page. It asks a different approver only where its gate says so, or where a setting lists the action, which the operator sets and a tenant may add to. A service principal never answers it.

ADR-0030's settings only narrow down the layers: a number is lowered, a subset shrunk, and a subset's layers resolve as their intersection. A setting of the tiers that need a person narrows what may happen by naming more. Its layers must resolve as their union, the direction no kind had.

## Decision

- **A third kind of setting, `Superset`,** in `lattice_core.settings`:
  - It holds some of a set of known names, as `Subset` does, but its names are what a layer asks for. A lower layer may only add names, and the layers resolve as their union.
  - The layer above's value is the least a lower one may hold. A value without every one of its names is refused where it is written, and clamped where it is read.
  - Its floor, what an unreadable store answers, is every name, so a store that can't be read asks for everything.
  - grantr's settings carry it as `type: "superset"`. A refusal says what the value must keep (`approve:tiers must keep outbound here: the operator's value`), and portalr's settings page keeps the names the layer above asks for checked and disabled.
- **`approve:tiers`,** in `KNOWN_SETTINGS`:
  - A `Superset` of the capability tiers that need a person's approval.
  - Default `outbound` and `run_code`; `read` and `write` need no one until a layer asks.
  - Set at every layer.
- **`admin-high:different-approver`,** declared by the application with `admin_high_approvers(capabilities)`:
  - A `Superset` of its registered `admin_high` capabilities whose calls need a different approver. None does by default.
  - The operator's value names those that do everywhere, and a tenant may add others, never take one away.
  - Its universe is the application's capabilities, as artifactr's `agent-writes:direct` is the application's types, so lattice-core can't declare it.
- **`SettingsPolicy(settings, action="grantr:answer_approval")`,** lattice's `ApprovalPolicy`:
  - **An `admin_high` capability** asks the caller's own confirmation: the person who called, or the person the run or session acts for, on `portalr:confirm`.
    - Where its gate's `different_approver` says so, or `admin-high:different-approver` names it, it asks a different approver: any holder of the action but the caller.
    - A caller acting for no person, who can't confirm, also asks a holder of the action.
    - This holds whatever the tiers.
  - **Any other capability** asks a person only where `approve:tiers` names its tier: any holder of the action, or the person the call acts for.
    - It asks a different approver where its gate says so, or where it is `outbound` and the caller is tainted.
  - **A setting it can't read raises,** which refuses the call. An application with `admin_high` capabilities that doesn't declare `admin-high:different-approver` refuses every call of them.
- **grantr's store keeps the rest** (grantr ADR-0038). A confirmation is answered only by its one named person, on `portalr:confirm`, and never by a service principal; a different approver is never the person who asked.

## Options considered

### Option A: A union kind of setting (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a kind in lattice-core, its wire type in grantr, its control in portalr |
| Safety | An unreadable store asks for every tier |
| Fit | Every layer is read, written, versioned and audited as every setting is |

**Pros:** asking more is narrowing, as ADR-0030 has it; only the direction of the names differs.
**Cons:** a third kind for every reader of settings to handle.

### Option B: Invert the names, a `Subset` of the tiers that need no person

**Pros:** no new kind.
**Cons:** the operator's value would list what is let through, so a tier added to the capabilities later would need no approval until someone removed it. An admin reading "tiers that need no approval" checks the opposite of what they mean.

### Option C: The operator's alone in 0.3.0

**Cons:** RFC-0011 decided O5 the other way: a tenant that wants a person on writes would have to ask its operator.

## Trade-off analysis

Option A keeps one rule for every setting: a lower layer narrows. A new tier is asked by default only if the operator lists it, and an unreadable store asks for everything, where Option B's would let everything through. A default of `outbound` and `run_code` asks a person before an agent reaches outside or runs code, and leaves reads and writes to the gates, the taint policy and artifactr's proposals until a layer asks more.

## Consequences

- Easier: a tenant asks approval of more tiers in admin, and the operator sets a floor in configuration.
- Easier: an `admin_high` action is confirmed by the person who called, so a sole owner can still revoke a leaked key or delete their tenant.
- Harder: every reader of settings handles a third kind; grantr's and portalr's do.
- The default deadline stays the enforcer's `approve_within`; RFC-0011's `approve-within` setting is its own change.
- An admin action reached through an outside client is confirmed on portalr's page, never by the client; portalr's confirm page is its own change.

## Action items

1. [x] `Superset`, `approve:tiers`, `admin_high_approvers` and `SettingsPolicy`, tested; grantr's wire type and refusal, and portalr's control.
2. [ ] portalr's confirm page, answering a confirmation on `portalr:confirm`.
3. [ ] The `approve-within` setting, read by the enforcer for an approval's deadline.
