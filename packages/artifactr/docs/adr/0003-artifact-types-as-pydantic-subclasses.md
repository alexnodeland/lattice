# ADR-0003: Artifact types are Pydantic subclasses with library-defined patch kinds

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Downstream projects must be able to add artifact types easily; that is the library's main extension point. Without a per-type interface, type-specific behaviour tends to scatter across the codebase as comparisons on a type-name string, and every new type touches many files.

Edits come from both people and language models, and models are markedly more reliable with some edit forms than others. JSON Patch paths that address list items by index break as soon as the list changes. Replacing an exact, unique string in a document works well.

## Decision

An artifact type is a **Pydantic model subclass**:

```python
class Plan(Artifact):
    write_policy: ClassVar[WritePolicy] = "propose"
    tasks: dict[str, Task] = {}

    def render_for_agent(self) -> str: ...
```

- Configuration is class variables (`write_policy`); behaviour is methods (`render_for_agent`, domain mutators such as `add_task`).
- Types register themselves in `__pydantic_init_subclass__`, which runs after Pydantic has built the fields. The type name is derived from the class name (`ReleaseNotes` becomes `release_notes`) and can be overridden with a `name=` class argument, matching pydantic-ai's `CustomEvent` convention.
- Stored instances are `Versioned[T]`. `Versioned[T].edit(fn)` copies the data, lets `fn` mutate the copy, and diffs the result into a command against the current version.
- The library defines two patch kinds: **JSON Patch** (RFC 6902) for `Artifact`, and **anchored text edits** for `MarkdownArtifact`. Types cannot define their own patch kinds.
- Collections the agent edits should be id-keyed mappings, not lists, so patch paths stay stable.
- Agents never write raw JSON Patch. Applications give them domain tools, and documents get a generic text-edit tool.

## Options considered

### Option A: Pydantic subclass (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one class per type |
| Extensibility | High for data and behaviour; patch kinds fixed |
| Validation | Pydantic's own, including custom validators |

**Pros:** idiomatic; one class per type; registration is automatic.
**Cons:** data and behaviour live on the same class.

### Option B: A separate `ArtifactType[TData, TPatch]` class paired with a data model

| Dimension | Assessment |
|---|---|
| Complexity | Medium: two classes per type, generics throughout |
| Extensibility | High, including custom patch kinds |
| Validation | Pydantic, via the paired model |

**Pros:** explicit separation of data and behaviour.
**Cons:** twice the classes; manual registration; more surface to learn.

### Option C: Types define their own patch kinds (`apply` and `diff` per type)

| Dimension | Assessment |
|---|---|
| Complexity | High for type authors |
| Extensibility | Highest |
| Validation | Depends on each implementation |

**Pros:** any edit semantics are possible.
**Cons:** every type author must write correct apply and diff logic; conflict and rebase behaviour varies by type.

### Option D: Untyped JSON with a registry of validators

| Dimension | Assessment |
|---|---|
| Complexity | Low at first |
| Extensibility | Poor: behaviour ends up in string comparisons |
| Validation | Only what is registered; unknown types pass through |

**Pros:** easy to start.
**Cons:** no place for per-type behaviour.

## Trade-off analysis

Option A puts everything about a type in one idiomatic class and lets Pydantic do the validation it is best at. The cost is that new patch semantics need a library change. With JSON Patch for structured data and anchored text edits for documents, that covers turn-based collaboration; true simultaneous editing would need CRDT-backed types, which would be a library-level addition in any case.

## Consequences

- Easier: a new type is one class; everything else comes from the library.
- Easier: conflict and rebase behaviour is uniform across types.
- Harder: types that need edit semantics beyond the two patch kinds need a library change.
- Harder: lists edited by index are discouraged; type authors should use id-keyed mappings.

## Action items

1. [ ] Implement `Artifact`, `MarkdownArtifact`, registration and `Versioned[T]` in core.
2. [ ] Implement JSON Patch apply and diff (via `jsonpatch`) and anchored text edits.
3. [ ] Property-test patch round-trips with hypothesis.
