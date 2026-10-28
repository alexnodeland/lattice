# ADR-0019: The agent creates native files

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0017](0017-a-persons-upload-told-by-its-bytes-read-before-it-is-committed.md), whose agent got no tool to make a file; [ADR-0006](0006-the-agents-tools-behind-each-apps-switch.md), whose toolset only read and edited files; and [ADR-0012](0012-an-app-for-each-type-and-no-format-changed-by-a-check-in.md), whose `enabled(ws, type)` now also says which types the agent may create

## Context

An agent could read and edit a native file, but never start one: asked to "write up a travel plan as a docx and a pptx", it had nothing to edit until a person uploaded a file. [ADR-0017](0017-a-persons-upload-told-by-its-bytes-read-before-it-is-committed.md) gave it no tool to upload, since a model never sends a file's bytes, and that still holds. But every app's port already makes a file from nothing, `App.apply(None, commands)` ([ADR-0004](0004-an-app-is-a-port-of-stateless-calls.md)), which the crafting apps' adapters answer with an empty, untitled file of their format, as the [native files guide](../guides/native-files.md) says of each. Issue 874 asked for a tool over it.

A native type's write policy is `propose`, so an agent's create, committed as the agent, would be a proposal: a reviewer asked to accept an empty file, before the edit that matters, is a step that tells them nothing.

## Decision

- **`NativeFiles.create(ws, file_type, name, *, artifact_id, thread_id)`** makes a blank file, beside `upload`. It asks `authorize`, as the handle's actor, `artifactr:create_native_file` and `artifactr:create_artifact` before anything else; then the app's switch (`NotEnabled`); then holds a place and the actor's pace (below); then has the app make the file, `apply(None, [])`, in one of the tenant's readings (`Busy`). Its format is the one the app names, or the type's only one; any other, or none named for a type of several, is `ValidationFailed`, never the app's text. Its size is held to its format's most (`TooLarge`). The bytes and what the app read are put as an upload's are, all or none and held to the quotas (`OverQuota`), and one `create_artifact` is committed. The first bytes are not sniffed: the app made them. Its provenance is a new source, **`blank`**, with the app, its version and build, and, when it is committed for an agent's run, the agent and its run (`Provenance.agent`, `run_id`). Given the id of a file of the type that is there, it makes nothing and returns None, before the app is called or the pace or quota spent; an id taken by another artifact, or by one the actor can't see, is `AlreadyExists`. The id never depends on the bytes, which a craft stamps with the time.
- **Creating is applied, editing is proposed.** An agent's run commits the file as the person it acts for, its `on_behalf_of`, through a handle as them, so it is applied whatever the type's write policy; that commit asks `authorize` as the person too, so both are checked. The agent's edits of it then follow the policy, `propose` by default. A run that acts for no one commits as itself, and one for a person's client as the client, each under the policy, which proposes. A tenant still narrows creation away from the agent by refusing it either action. The person is the revision's actor and the log's, so the agent is recorded beside them: in the file's provenance, `agent` and `run_id`, and on the tool's span, which carries the run and the person. A thread in `suggest` mode doesn't hold a blank create for review either: an empty file has nothing to review, and the edits that follow are held.
- **Its pace and places are an upload's.** `Pace` and `Gauge` move from the router to `artifactr.files.native`, and `NativeFiles(pace=, gauge=)` takes them, both None by default. `create` holds the actor it commits as to them, so an agent's run spends its person's pace and share as their uploads do, the place first, as the router does, and refuses with `Paced` (its `wait`, or None when every place is held). `files_router` uses the ones `NativeFiles` carries in place of its own, so an agent's files and a person's uploads count against one pace and one set of places; without them it builds its own from its arguments, as before, and its statuses and API are unchanged.
- **`create_native_file(type, title)`** is one tool, in `native_file_tools`. Its description lists, each step, the types whose app is on in the run's workspace, each as its kind, extensions and a noun (`NativeFile.noun`, such as `a Word document`), and its `type` is an enum of those kinds; a type not listed is refused in a sentence. Its file's id is derived from the run and the tool call's id, so a call retried after it succeeded makes one file and is told the same answer. One run segment creates at most ten files (`native_file_tools(creates=)`), past which it is told so, so a looping or misled agent never spends its person's whole pace or quota. It follows the new file, so the agent hears of changes to it, marks it on the tool's span, and says `Created <id>: a Word document named Travel plan.docx, at version 1. Edit it with edit_native.` Every refusal is a sentence, not a retry, since none is fixed by calling again at once: forbidden or off, paced, busy, over a quota, too large, of another format, a craft that makes no blank file (`refused`), or a worker down. The toolset is still hidden while every app is off.
- **ADR-0017's "the agent gets no tool to upload" stands** for bytes: the model still never sends a file's bytes, and the app makes every byte of a blank file.

## Options considered

### Option A: Commit as the run's person (chosen)

| Dimension | Assessment |
|---|---|
| Scope | `NativeFiles.create` alone; no rule, command or surface changes |
| Checks | The agent's and the person's, both |
| Record | The revision's actor is the person; the provenance says the app made it blank |

**Pros:** Narrow: nothing else an agent commits changes. The precedent is portalr's `draft_document`, which uploads as the person it acts for.
**Cons:** The revision names the person, not the agent, which is recorded in the provenance and on the span instead.

### Option B: A per-type create policy in the rules

A `create_policy` beside `write_policy`, `direct` for native types. **Cons:** an agent's `create_artifact` on REST or MCP, with a manifest of its own naming any digest, would then be applied too, past `artifactr:create_native_file`, unless every surface learned the difference.

### Option C: Keep it a proposal

**Cons:** the reviewer accepts an empty file before anything worth reviewing, and the agent can't edit it until they do: what issue 874's owner decided against.

## Trade-off analysis

Option A changes who a create is committed as in one method, and keeps every other path of the agent's under its policy. Option B is cleaner in the record but opens a path for any agent surface. The person's request is what the file answers, so they are its first revision's actor; the agent and run that made the request are recorded in the provenance, the app that made the bytes in its `blank` source, so nothing about who did what is lost, though a reader of the log alone sees the person.

## Consequences

- An agent starts a file of any type whose app is on, and edits it by proposal.
- Applications that want the tool's pace pass `NativeFiles(pace=Pace(20), gauge=Gauge(8, tenant=4, each=2))`, which the router then shares. stackr's template wires it, and FilmCraft, EffectCraft and SoundCraft, in follow-ups.
- A run's watcher would hear its own file's creation as the person's, a change by another in its thread. The tool adds the file's id to the session's `made` before it commits, and the watcher skips the creation of an id there, so the agent is told once, by the tool, and the file keeps its thread.
- Only the fake app is tested making a blank file here; each craft's blank file is tested live in a follow-up.
