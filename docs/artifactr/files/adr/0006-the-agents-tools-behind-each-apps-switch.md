# ADR-0006: The agent's tools, behind each app's switch

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records the agent's half of phase 3 of [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md#what-the-agent-sees), and how native files answer to the shared Integrations switch ([lattice ADR-0027](../../../adr/0027-integrations-switched-per-workspace-through-one-port.md)).

## Context

RFC-0003 gives the agent five tools beside artifactr's own: the file's words, its review, its look, the app's commands, and an edit by a batch of them. An agent that meets a person's check-out must plan again after the check-in, not retry at once, and must never queue a proposal stale on arrival.

lattice-core's `Integrations` port answers whether an integration is on in a tenant's workspace, and its registry declares each crafting app as one: `files:wordcraft` first. artifactr's `integration_gate` refuses, before `authorize`, a command that makes or changes what an integration governs while it is off (artifactr ADR-0081). Each `App` names its key, `integration` ([ADR-0005](0005-wordcraft-headless-pinned-by-checksum.md)).

## Decision

- **`NativeFiles` takes an `Integrations`,** and asks it for its app's key in the workspace of each write: an upload, a check-out, an extension, a check-in and an edit are refused with `NotEnabled` while the app is off, before any lease is taken. Reads and collection go on, as artifactr's gate lets reads through. Without one, every app is on, as without a store each key is its default.
- **`NativeFiles.key_of` is the gate's `key_of`:** the app's key for any native file's kind, and None for any other. It assumes one app a deployment, as the pilot has; a second app's adapter will have to say which formats are its. An application that passes `integration_gate(integrations, files.key_of)` to `Workspaces` refuses an edit of a native file while its app is off on every surface, REST, MCP and the agent's generic tools alike, not only through `NativeFiles`.
- **`native_file_tools(files, view=False)` is the toolset,** a pydantic-ai `FunctionToolset` over the run's `Session`, as `artifact_tools` is:
  - `read_native(artifact_id, start)`: the text blob, 8,000 characters a call, saying where to read on.
  - `read_review(artifact_id, start)`: comments and tracked changes, 50 a call, each marked as one or the other, as the app gives them: WordCraft's, and the fake's, with their ids.
  - `find_commands(query)`: the app's commands, ten at most.
  - `edit_native(artifact_id, base_version, commands, summary)`: one batch, through `NativeFiles.edit`.
  - `view_page(artifact_id, page)`: one rendered page, as an image; offered only with `view=True`.
- **The toolset is offered only while the app is on** in the run's workspace, through the toolset's `prepared`, which reads the switch once a step, so a model where it is off never sees its tools.
- **A person's check-out is an answer, not a retry.** `edit_native` returns who has the file and until when, and tells the agent to plan again once it is checked in. Another agent's edit, which holds the file for seconds, and a lease that ended before it was read are `ArtifactBusy` as it is, which artifactr's capability turns into a retry. The app's refusal is a retry with its reason; a timeout, a crash or a file too large fails the call, since retrying at once won't help. A stale base is artifactr's `VersionConflict`, which the capability turns into "read the artifact again".
- **The layer is `artifactr.files.tools`,** the only one of the extra's that imports `artifactr.agent` and pydantic-ai.

## Options considered

### Option A: Gate in `NativeFiles` and on the workspace, and hide the tools (chosen)

| Dimension | Assessment |
|---|---|
| Coverage | Every write path is refused while off: the package's, and any surface's through the gate |
| Model | Sees no tool it can't use |
| Cost | One switch read a write in `NativeFiles`, and one more at commit with the gate; one a step for the tools |

### Option B: Only artifactr's gate

**Cons:** a check-out commits nothing, so the gate never hears it: a person could check a file out, and hold its lease, where the app is off.

### Option C: Refuse in the tools, and offer them always

**Cons:** the model spends calls learning, by refusal, what the run could have told it.

## Trade-off analysis

The switch is read where a write starts, and where a tool is offered: cheap, as its port asks, and the only places a write can begin.

## Consequences

- Easier: a workspace whose admin switches WordCraft off has no check-outs, edits or tools for it, and keeps its files' history readable.
- Harder: an application must pass the same `Integrations` to `NativeFiles` and to the gate; the guide shows both.
- Harder: while the app is off, a check-out can't be checked in or extended either; its lease lapses on its own, and the person's copy stays on their disk.
- RFC-0003 names `read_native`'s second argument `pages`, but the text blob has no page breaks, so it reads on by character instead.
- Deferred: the worker, its image and stackr's recipe, and the hostile corpus, phase 3's sandbox; until then the app is `Subprocess`, for trusted files.

## Action items

1. [x] `NativeFiles(integrations=)`, `enabled`, `key_of` and `render`.
2. [x] `native_file_tools`, with scripted-model tests for an edit, a proposal, a busy refusal and a conflict.
3. [ ] The worker, its image and recipe, and the hostile corpus.
