# ADR-0035: One approval per call, bound to its arguments, declared in lattice-core and stored by grantr

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland
**Records:** [lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s Decisions T2, T3, O11, O12 and, for approvals, O14, as the approval contract `lattice_core.approvals` declares them

## Context

v0.3 asks people to approve calls on several surfaces: portalr's card, a phone's web push, an MCP client's elicitation, and later Slack ([#941](https://github.com/alexnodeland/lattice/issues/941)). artifactr's deferred tools pause a run for an answer in the chat. Without one object, each surface would ask, record and expire approvals its own way, and the same call could be approved twice, or approved on one surface after being denied on another. RFC-0011 makes the approval one object, declared in lattice-core beside the capability registry ([ADR-0032](0032-the-capability-registry-in-lattice-core-four-tiers-three-effects-and-entry-points.md)). The owner decided where it is stored, how delegation works, and the two shapes it needs for plans and for "always allow", on 2026-10-30 and 2026-10-31.

## Decision

- **One approval per call, declared in lattice-core (`lattice_core.approvals`), `CONTRACT` 1.0.0,** with its JSON Schema at `packages/lattice-core/schemas/approvals.v1.json`. An `Approval` is one call of one capability, by name and version, in one `Scope`. It carries a `Rendering` of exactly what would happen (a title, a summary, and a diff or the arguments), the SHA-256 of the call's canonical arguments, who asked (the call's `Caller`), who may answer (`Answerers`), a deadline, and its state: `pending`, `approved`, `denied`, `expired` or `withdrawn`.
- **An answer binds to what was shown.** An `Answer` carries the digest of the arguments its person saw, and one given to other arguments is refused (`DigestMismatch`). A replanned call is a new approval. The store records who answered and when, as `Answered`.
- **The first answer wins.** A store's `answer` is a compare-and-set on a pending approval, in one transaction with its audit entry, and a later answer gets `AlreadyAnswered` with the first. An approval that expired or was withdrawn takes no answer (`NotPending`).
- **Stored by grantr (T2),** whose subjects already say who may answer, and which already keeps an audited store per tenant. lattice-core holds the `Approvals` port and `FakeApprovals`, an in-memory store with the same semantics; grantr's store comes in RFC-0011's phase 3, and an application without grantr has the fake only.
- **Delegation is a grantr grant with an expiry (T3),** never a field of the approval. `Answerers` name a grantr action, subjects or groups, so whoever holds the action may answer, and "Sam answers mine this week" is a grant of it to Sam until Friday. A different approver is never the person who asked. A service principal answers only where it is named or granted the action itself.
- **The caller's own confirmation is a kind of answerers.** `Answerers(confirmation=True)` names the one person who called, or whom the run acts for, and is answered only by them on portalr's signed-in confirm page (`CONFIRM_SURFACE`), never by a service principal. When an `admin_high` call asks for one, and when a different approver is required instead, is the approval policy's, recorded with its settings in phase 3.
- **A plan's approval covers what the plan lists (O11).** `covers` holds `ListedAction` entries: a step, the capability's name, major version and tier, a target over its arguments as JSON, the calls allowed, and a digest of all of these with the capability's whole definition, so a capability that changes is no longer covered. The enforcer asks a `Coverage` before it asks a new approval; reflexr answers it for plans (lattice RFC-0012), and `NoCoverage`, which covers nothing, is the default.
- **Scoped answers have their shape now (O12).** An `AnswerScope` says how long an answer stands (`session` or `run`), for which patterns, and until when. A request offers the patterns a scope may name (`scopes_offered`, empty by default), and an answer naming one not offered is refused (`ScopeNotOffered`). Nothing offers a scope in 0.3.0, and grantr's store refuses every scoped answer until the code sessions' "always" is built in 0.3.x.
- **A request names the client it came through (O14).** `ApprovalRequest.via` is the call's `Via`, so a different approver's approval is never offered back through the client that made the call, and audit names it.
- **Policies, coverage and surfaces are ports.** `ApprovalPolicy.needed(capability, context)` returns the answerers a call needs, or None. `ApprovalSurface.offer` and `resolved` are how a store reaches portalr, web push and the rest.

## Options considered

| Option | For | Against |
|---|---|---|
| **Stored by grantr (chosen)** | Its subjects define who may answer; it already has audited, per-tenant stores | Approvals depend on grantr; without it, only the fake |
| Stored by artifactr, beside deferred tools | Where the first approvals are today | reflexr and portr couldn't reach it |
| A new package | Independent of grantr | One more release for one table |
| **Delegation as a grant with an expiry (chosen)** | grantr checks it, and it expires on its own | A delegation isn't visible on the approval itself |
| A delegate field on each approval | Visible where it applies | grantr couldn't check it |
| **`covers` and a `Coverage` port (chosen)** | A plan approved once runs without asking again for what it listed | The coverage check is one more port at the enforcer's step 6 |
| An approval per listed action at each step | Nothing new | A plan of ten actions asks ten times |
| **`AnswerScope` now (chosen)** | The store's schema is fixed with it before 0.3.0 | A shape nothing uses until 0.3.x |
| `AnswerScope` when 0.3.x needs it | Nothing unused in 0.3.0 | The store's schema would change after release |

## Consequences

- Easier: every surface answers the same object, so a run paused on one approval resumes whichever surface answered, and every surface shows the first answer.
- Easier: a plan approved once covers its listed actions, and anything it doesn't list, or that changed, still asks.
- Harder: an application without grantr has only the in-memory store.
- Harder: the readings this contract takes of RFC-0011's sketch are part of version 1 (the pull request that adds it lists them): a removed field or changed meaning is a major version.
- Follow-ups, in RFC-0011's phases: the enforcer's step 6 asking `Coverage` and then the store (phase 2); grantr's store, its race test on SQLite and PostgreSQL, expiry and audit, and the `admin_high` policy with `admin-high:different-approver` (phase 3); reflexr's `Coverage` for plans (RFC-0012); the surfaces beyond portalr's card (M3 and M4).
