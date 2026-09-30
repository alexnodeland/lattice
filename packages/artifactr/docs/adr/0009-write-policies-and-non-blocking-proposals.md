# ADR-0009: Write policies and non-blocking proposals

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Some artifact types should accept the agent's edits directly, such as a scratch draft. Others warrant review, such as a plan or a spec. People sometimes want the agent in "suggest" mode for everything. When a proposal blocks the agent until someone decides, the agent stalls. When a person accepts a proposal with edits, the agent must see those edits, not its original suggestion.

## Decision

- Each artifact type declares `write_policy: ClassVar[Literal["direct", "propose"]]`. A thread in suggest mode forces proposals for every type.
- `Workspace.commit` applies the policy and returns `Applied` or `Proposed`. Tools handle both, typically with an exhaustive `match`.
- **Proposals are durable workspace objects and do not block the run.** Any surface resolves them with `respond_to_proposal` (accept or reject, optionally with changes). `core.respond` rebases the accepted patch onto the current version.
- The outcome reaches the agent as a change note ([ADR-0008](0008-agent-perception-and-steering.md)). When a proposal is accepted with changes, the note includes the person's changes as a diff.
- pydantic-ai's deferred tools are reserved for genuinely blocking points ([ADR-0010](0010-pausing-with-deferred-tools.md)).

## Options considered

### Option A: A per-type policy with a thread-mode override; non-blocking proposals (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Human control | Configurable per type and per thread |
| Agent flow | Uninterrupted |

**Pros:** review where it matters; the agent keeps working; the person's edits reach the agent.
**Cons:** tools handle two outcomes; UIs need a review surface.

### Option B: Always direct, with undo

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Human control | After the fact only |
| Agent flow | Uninterrupted |

**Pros:** smoothest flow.
**Cons:** no review before a change lands.

### Option C: Always propose

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Human control | Maximum |
| Agent flow | Uninterrupted, but noisy |

**Pros:** nothing changes without consent.
**Cons:** friction on low-stakes artifacts.

### Option D: Proposals as blocking approvals (deferred tools)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one mechanism |
| Human control | Maximum |
| Agent flow | Stops at every suggestion |

**Pros:** one pause mechanism for everything.
**Cons:** the agent cannot continue while a suggestion is pending; "accept with edits" squeezes into an argument override.

## Trade-off analysis

Review belongs to the artifact's nature, so the policy belongs on the type, with the thread mode as a person's override. Keeping proposals out of the pause mechanism lets the agent carry on, for example drafting the doc while the plan awaits review, and it lets a decision arrive whenever it arrives.

## Consequences

- Easier: suggestion mode is one switch; review is uniform across types.
- Harder: pending proposals can go stale. Accepting then rebases, or it conflicts and the person resolves it.
- Revisit whether some proposals should expire.

## Action items

1. [ ] Implement policy handling in `core.commit`, and `core.respond` with rebasing.
2. [ ] Emit change notes for resolved proposals, including the person's diff.
3. [ ] Add conformance fixtures for each policy, mode and outcome.
