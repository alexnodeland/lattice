# ADR-0078: The agent's toolset for forms, and no apps yet

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) gives the agent `ask_form`, `create_form`, `show_dashboard` and `update_dashboard` in phase 1, as an application toolset ([ADR-0017](0017-application-toolsets-and-capability-events.md)), and `make_app` and `update_app` only in phase 2, when the application turns apps on.

## Decision

- **`artifactr.ui.agent.ui_tools(*, forms=True, dashboards=True)`.** It has no `apps` parameter: phase 2 adds it with its tools, rather than a parameter that refuses itself now.
- **Each tool validates what the model wrote before anything is recorded,** and gives a refusal back as `ModelRetry` whose message names every field and keyword, since `ArtifactWorkspace` turns a core refusal into a retry with its message alone.
- **`ask_form` raises `CallDeferred`,** so the request's `args` are the tool's own: `title`, `schema`, `ui`. It is a question; its answer is the tool's result when the run resumes.
- **`show_dashboard` and `update_dashboard` write `as_of` as the moment they run,** since a snapshot is true when the agent wrote it.
- **The tools' descriptions describe the subset in words, from its limits,** and give the panels' JSON Schema, so they never change between requests.
- **`AGENT_TYPES`, `(Form, Dashboard)`, is what the agent's `ArtifactWorkspace` takes:** its generic tools then make and edit forms and dashboards, and never a submission, which is a person's, or an app, which phase 2 offers through tools of its own. `UI_TYPES` is for `Workspaces(types=...)`.

## Consequences

- Easier: a model learns the subset from the description and from each refusal.
- Revisit: phase 2's `make_app`, offered while `ui:mini-apps` is on ([ADR-0080](0080-integrations-on-or-off-per-workspace.md)).
