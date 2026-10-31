# ADR-0099: artifactr's tools as capabilities, called through the enforcer, whose policy asks approval

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md) makes every tool an agent can call a capability, offered through lattice-core's registry and called only through its enforcer ([lattice ADR-0032](../../adr/0032-the-capability-registry-in-lattice-core-four-tiers-three-effects-and-entry-points.md), [lattice ADR-0037](../../adr/0037-the-enforcement-path-in-lattice-core-refusals-by-step-approvals-resumed-by-id.md)). Its phase 2 needs one provider from artifactr ([#940](https://github.com/alexnodeland/lattice/issues/940)), and its Decision T5 settles how artifactr's own tools are approved: "`requires_approval` stays as the mechanism, and the enforcer sets it from the policy", rather than each tool declaring its approval beside a policy that may disagree.

Today artifactr's agent declares no approval on its artifact tools. A connected app's code and network tools ask one on every call, with a review the person reads (ADR-0085), and `ask_user` pauses a run for answers (ADR-0083). pydantic-ai pauses a run for a tool's approval when the tool raises `ApprovalRequired`; `requires_approval=True` is the same pause, declared on the tool.

## Decision

`artifactr.capabilities.ArtifactrProvider` offers artifactr's artifact tools as `command` capabilities, named `artifactr.<tool>`, each at version 1.0.0:

| Capability | Tier | Effects | Reversibility | Gate |
|---|---|---|---|---|
| `artifactr.list_artifacts` | `read` | `reads_private` | none | `artifactr:read_artifacts` |
| `artifactr.read_artifact` | `read` | `reads_private` | none | `artifactr:read_artifacts` |
| `artifactr.create_artifact` | `write` | none | compensable: archive it | `artifactr:create_artifact` |
| `artifactr.edit_text` | `write` | none | compensable: edit it back | `artifactr:edit_artifact` |
| `artifactr.propose_text` | `write` | none | undoable: nothing changes until accepted | `artifactr:propose_change` |
| `artifactr.archive_artifact` | `write` | none | irreversible: nothing unarchives | `artifactr:archive_artifact` |

- **No integration gates them,** since artifactr is always installed. Proposing is a capability of its own, not an argument of `edit_text`, so each grantr action gates one capability, and a policy can approve a proposal more readily than an edit.
- **They're for callers outside artifactr's own threads:** another library's agent, a code session, a person's outside client. The provider opens the call's workspace as the actor `actor_for` builds from the call's context. A call through an outside client is that client's `ExternalAgentActor`, for the person (lattice RFC-0014). A person's own call is their `UserActor`. An agent's run is `ExternalAgentActor("agent:<agent>")` and a code session's is `"session:<id>"`, each for the person it acts for. An application may build the actor itself. Each command commits in no thread, so the workspace's `authorize`, gate and checks hear it again after the enforcer's steps.
- **T5: no artifactr capability declares an approval.** Whether a call needs one is the application's `ApprovalPolicy`'s, asked at the enforcer's step 6. A call it defers raises `ApprovalRequired` through lattice-core's agents bridge, the pause `requires_approval` declares, so a run pauses and resumes as artifactr's runner already handles. "The enforcer sets it from the policy" is read as the enforcer raising the pause from the policy at call time, since the policy depends on the call's context (its taint, and whether a plan covers it), which no flag fixed at definition time can hold.
- **A connected app's risk maps to a tier:** `read` to `read`, `edit` to `write`, `code` to `run_code`, `network` to `outbound`, and `host` to none, since it is never offered (`artifactr.connect.TIERS`). The protected risks are exactly the tiers that run code or reach outside. A connected app's tools aren't capabilities yet: a provider lists its capabilities without waiting, and a connected app's are known only by asking its live server.
- **The application composes the provider by hand,** as RFC-0011 allows (T6). It needs the application's `Workspaces` and artifact types, so it isn't named as an entry point that `discover()` loads with no arguments.
- **One suite holds every provider to the enforcer** (lattice's `tests/test_enforcement_suite.py`): tiers, grants, limits, taint, approvals, coverage and audit, on a fake provider of each kind and on artifactr's. A covered call asks nothing, and a different approver's call, a confirmation and a taint `ask` are never covered.

## Options considered

| Option | For | Against |
|---|---|---|
| **The policy raises the pause at call time (chosen)** | One place decides; it sees the taint and coverage | A tool's definition doesn't say whether it will ask |
| `requires_approval` set on each tool from the policy when the toolset is built | The flag artifactr's tools would carry | Fixed per run step, blind to each call's taint and to plans |
| Each tool declaring its approval (today's connected apps) | Visible on the tool | Two places decide, and they can disagree (T5's rejected option) |
| **`propose_text` beside `edit_text` (chosen)** | Each grantr action gates one capability | Six capabilities, not five |
| `propose` as an argument of `edit_text` | The agent's own tool's shape | The gate checks `edit_artifact` for a proposal, which `propose_change` governs |

## Consequences

- Easier: another library's agent, a code session or an outside client reaches artifacts through the one path every capability takes, with its approval, limits, taint and audit.
- Easier: an application decides approvals for artifactr's tools in its policy, beside every other library's.
- Harder: artifactr's own thread agent still uses its own toolset (`ArtifactWorkspace`), whose tools don't go through the enforcer. Moving it onto the bridge needs the runner to carry an approval's id back as it resumes, and `answer_deferred` to answer the approval's store.
- Harder: a connected app's code and network tools keep their own approval (ADR-0085) until they become capabilities.
- Follow-ups: grantr's `Authorize`, `Audit` and approvals store (RFC-0011's phase 3); artifactr's runner on the bridge, with `answer_deferred` answering `Approvals` (phase 3); connected apps as capabilities; reflexr's and grantr's providers, and the cross-package bypass test (phase 6).
