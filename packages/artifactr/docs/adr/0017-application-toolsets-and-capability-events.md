# ADR-0017: Application toolsets register on the agent; the capability emits capability events

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0006](0006-agent-integration-as-pydantic-ai-capability.md)

## Context

[ADR-0006](0006-agent-integration-as-pydantic-ai-capability.md) planned for `ArtifactWorkspace.get_toolset` to contribute the generic artifact tools *plus the application's toolsets*.

A spike against pydantic-ai 2.51 confirmed the rest of the design (dynamic instructions re-render on every model request; `for_run` and `wrap_run` can hold a background task for the run's lifetime; `ctx.enqueue` from that task reaches the next model request). It also surfaced a rule the plan conflicted with. pydantic-ai separates two event families:

- **`CapabilityEvent`**: namespaced events that only a capability's hooks and capability-contributed tools may emit.
- **`CustomEvent`**: application events that application tools emit. A capability-contributed tool that emits one raises `UserError`.

Routing application toolsets through the capability would make every application tool capability-owned, so application tools could no longer emit their own `CustomEvent`s.

## Decision

- **Application toolsets are registered on the agent**, the ordinary pydantic-ai way: `Agent(..., toolsets=[plan_tools], capabilities=[ArtifactWorkspace(types=[Doc, Plan])])`.
- `ArtifactWorkspace.get_toolset` contributes **only artifactr's generic tools** (list, read, edit document text, propose).
- artifactr's own events, emitted from its hooks and generic tools, are **`CapabilityEvent` subclasses in the `artifactr` namespace** (for example `ArtifactDraft`).
- Application tools emit `CustomEvent`s as usual. `forward_live` maps both families to live frames.

## Options considered

### Option A: Application toolsets on the agent (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Idiomatic | Yes: ordinary pydantic-ai usage |
| Application events | Work as documented by pydantic-ai |

**Pros:** application code needs no artifactr-specific conventions; event attribution is correct.
**Cons:** agent construction takes two arguments instead of one.

### Option B: Application toolsets through the capability, as ADR-0006 planned

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Idiomatic | No |
| Application events | Application tools must emit `CapabilityEvent`s in artifactr's namespace |

**Pros:** a single configuration point.
**Cons:** leaks artifactr's event namespace into application code, and misattributes application events to artifactr.

## Consequences

- Easier: application tools are plain pydantic-ai tools with no special rules.
- The architecture document's agent section is updated to match.

## Action items

1. [x] Update [architecture.md](../architecture.md) and the README example.
2. [ ] Implement the `artifactr` capability event family in RFC-0001 phase 3.
