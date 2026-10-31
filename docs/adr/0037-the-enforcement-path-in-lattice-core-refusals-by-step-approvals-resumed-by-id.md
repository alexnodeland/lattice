# ADR-0037: The enforcement path in lattice-core: refusals by step, approvals resumed by id

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland
**Records:** how [lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s "One enforcement path" and its agents bridge are built in `lattice_core.enforcement` and `lattice_core.agents`, where the RFC leaves the shape open

## Context

RFC-0011 makes `Enforcer.call(name, arguments, context)` the only way a capability is called: nine steps, each a port the application injects, with an approval step that defers a call and an agents bridge that offers capabilities to pydantic-ai agents ([#940](https://github.com/alexnodeland/lattice/issues/940)). The RFC names the steps and the ports, but not five things every caller depends on:

- what a refusal looks like;
- how a deferred call comes back;
- who answers a taint `ask`;
- how a failed call's taint gets back to the caller;
- what an agent sees as the tool's name.

## Decision

- **A refusal is a `Refused` naming its step:** `NotEnabled`, `Forbidden`, `TierRefused`, `LimitReached`, `TaintDenied`, `ApprovalClosed`, `WrongApproval`, and `UnknownCapability` at a `registry` step before the first. The first refusal stops the call, and no later step runs. A limit that can't be read or counted refuses, as ADR-0030 fails closed.
- **Every call is audited, refused or not,** with one `CapabilityCalled` entry: each step passed and the one that stopped it, the outcome (`called`, `failed`, `refused`, `pending`), the approval, and the arguments' digest. It never holds the arguments or the output.
- **A deferred call is resumed by the approval's id.** Step 6 asks the `Approvals` store and raises `ApprovalPending` with the new approval's id. The caller calls again with `approval=<id>`, and the enforcer reads that approval through the store's `get` and goes ahead only if it is for this capability and these arguments, and approved.
- **An approval lets one call through, and a try is counted once.** The enforcer takes the approval through the store's `take`, a compare-and-set, as the call goes ahead, and a second call on it is refused (`ApprovalClosed`). Step 4 counts a try against its limits when it is first made. A call resumed on its approval was counted as it asked for it, so it isn't counted again. `get` and `take` are added to the approvals contract ([ADR-0035](0035-one-approval-per-call-bound-to-its-arguments-declared-in-lattice-core-and-stored-by-grantr.md)'s amendment).
- **A taint `ask` is answered by the approval policy's answerers if it names any, otherwise by the person the call acts for.** With no person to ask, the call is refused. A taint `ask` is never covered by a plan's approval, and neither are a different approver's or a confirmation.
- **The enforcer holds no state.** The taint a call leaves comes back in `Called`, and a provider's error comes back as `CallFailed`, with the taint, marked, and the error as its cause. The caller keeps the taint for its next call.
- **Under pydantic-ai, a tool's name is its capability's with each `.` written `__`,** since model APIs allow only letters, digits, `_` and `-` (`artifactr.edit_text` is `artifactr__edit_text`). Two capabilities of one tool name in a scope are refused.
- **The agents bridge pauses on pydantic-ai's `ApprovalRequired`,** with the approval's id in its metadata under `approval`, the mechanism artifactr's connected apps already use. Resumed approved with that metadata, the tool calls the enforcer again with the id. Refusals and a provider's error reach the model as `ToolFailed`, and the run goes on. The bridge is a `DynamicToolset` rebuilt at each run step from the registry's capabilities in the run's scope, behind the `agents` extra (`pydantic-ai-slim>=2.53`).

## Options considered

| Option | For | Against |
|---|---|---|
| **Refusals as typed errors by step (chosen)** | A surface tells the reader which step said no; tests assert each | One error type per step |
| A result object with a refusal field | No exceptions | Every caller must check it, and a forgotten check calls nothing silently |
| **Resumed by the approval's id (chosen)** | The enforcer keeps nothing in memory; any surface's answer resumes it | The caller carries the id back |
| The enforcer waiting on the approval | One call | A run would hold memory and a connection for hours |
| **pydantic-ai's `ApprovalRequired` (chosen)** | artifactr's runner already pauses and resumes on it | The id travels in metadata, which a runner must give back |
| `CallDeferred` | Also pauses the run | The runner, not the tool, would have to call the enforcer on resume |

## Consequences

- Easier: every library's provider and every surface share one path, one audit and one set of refusals.
- Easier: a run paused on an approval resumes from whichever surface answered, with nothing waiting in memory.
- Harder: a runner must give back the approval's metadata when it resumes a call, and keep the taint a call leaves.
- Harder: a capability's name and its tool's name differ, so logs and surfaces that show both must say which.
- Follow-ups: artifactr's provider, `requires_approval` set by the policy (T5), and the runner keeping taint (phase 2's rest); grantr's `Authorize`, `Audit` and approvals store (phase 3); the cross-package bypass test (phase 6).
