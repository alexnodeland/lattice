# Forms and dashboards

This guide wires artifactr's forms and dashboards, `artifactr.ui`, into an application: the types, the checks, the agent's tools, and relayr's `ui:form_submitted` for rules ([lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md), [ADR-0074](../adr/0074-forms-and-dashboards-in-artifactr-ui-behind-the-forms-extra.md)).

## Install

```bash
uv add "artifactr-ai[forms]"     # forms, dashboards and the checks
uv add "relayr-ai[forms]"        # and ui:form_submitted for reflexr's rules
```

## Register the types, the checks and the tools

```python
from pydantic_ai import Agent, DeferredToolRequests

from artifactr import ArtifactWorkspace, Runner, Session, Workspaces
from artifactr.ui import AGENT_TYPES, UI_TYPES, ui_checks, ui_key_of
from artifactr.ui.agent import ui_tools
from artifactr.workspace import integration_gate


async def is_admin(workspace) -> bool:
    return await my_roles.is_admin(workspace.tenant_id, workspace.actor)


integrations = grants  # lattice-core's Integrations port: grantr's Grants, or Defaults()


workspaces = Workspaces(
    storage,
    types=[*app_types, *UI_TYPES],
    checks=ui_checks(is_admin=is_admin, integrations=integrations),
    gate=integration_gate(integrations, ui_key_of),
)
agent = Agent(
    model,
    deps_type=Session[None],
    output_type=[str, DeferredToolRequests],
    toolsets=[ui_tools(integrations=integrations)],
    capabilities=[ArtifactWorkspace(types=[*app_types, *AGENT_TYPES])],
)
runner = Runner(agent, app=None)
```

- **`output_type` includes `DeferredToolRequests`,** since `ask_form` pauses the run.
- **The workspaces take `UI_TYPES`, the agent's capability `AGENT_TYPES`:** the form and the dashboard. A submission is a person's, and an app is made through its own tools, so the agent's generic tools never make or edit either.
- **`is_admin`** says who may change any form's schema, policy or closing, and archive any form or submission, as their authors may. It is the application's, from grantr's roles or its own; without it, only a form's author may.
- **`integrations`** is lattice-core's `Integrations` port, grantr's store or `Defaults()`, which says whether forms (`ui:forms`), dashboards (`ui:dashboards`) or mini apps (`ui:mini-apps`, off by default) are on in a workspace ([ADR-0080](../adr/0080-integrations-on-or-off-per-workspace.md)). The gate, `integration_gate(integrations, ui_key_of)`, refuses making or changing their artifacts while one is off ([ADR-0081](../adr/0081-a-gate-before-access-integrations-switched-off-answer-not-enabled.md)); `ui_checks` refuses an answer to `ask_form` while forms are off, and `ui_tools` doesn't offer the agent their tools. Each refusal is `not_enabled`, whose payload names the `integration`; what exists still reads, and archives pass. Without it, each integration's default answers.
- **Checks of your own for the same command types** go in one check that calls both: `Workspaces` takes one check a command type.

## Ask a form

The agent calls `ask_form(title, schema, ui)`. A schema outside the subset goes back to the model as a retry naming each refused keyword, and nothing pauses. Otherwise the run pauses with a request whose `tool_name` is `ask_form` and whose `args` are the title, the schema and the hints; portalr renders it as a form. A person sends the values as an answer:

```python
await runner.answer(workspace, AnswerDeferred(run_id=run_id, tool_call_id=call_id, answer=values))
```

Values that don't fit are refused with `ValidationFailed`, each error's `loc` the property's name, and the run stays paused. A second answer is `InvalidState`. A chat message posted meanwhile answers nothing: it reaches the resumed turn beside the form's values.

## Forms that take submissions

`create_form(title, schema, ui, submissions)` makes a `form` artifact: `once` takes one submission in all, `per_person` one a person, and `many` any number. A person sends one as a `submission`, against the form's version, with its derived id:

```python
from artifactr.ui import submission_id

command = CreateArtifact(
    kind="submission",
    artifact_id=submission_id(form.id, principal=acting_for(actor).participant),  # per_person
    data={"form_id": form.id, "version": form.version, "values": values},
    thread_id=thread_id,
)
```

A `once` form's id is `submission_id(form.id)`, and a `many` form's `submission_id(form.id, nonce=nonce)`, with the nonce in the data too, made once per submit so a retry is the same submission; only a `many` form's carries a nonce. A form edited since its version is refused with `FormChanged`, and a closed one with `FormClosed`: both are `invalid_state`, and their payload's `reason`, `"changed"` or `"closed"`, says which. The agent, or a rule, reads submissions as artifacts of kind `submission`.

## Dashboards

`show_dashboard(title, panels)` makes a `dashboard`, true as of the moment it is made, and `update_dashboard(id, panels)` replaces its panels as its next version. Panels are `stat`, `bar`, `line` (up to three series), `donut`, `table` (up to 500 rows), `text` (Markdown) and `form` (a form artifact's id: a form with no fields is a button). A dashboard is at most 256 KB.

## Mini apps

Where a workspace switches `ui:mini-apps` on (it is off by default), `ui_tools` offers the agent `create_app(title, summary, html)` and `update_app(id, html, summary=None, title=None)` ([ADR-0082](../adr/0082-mini-apps-the-agents-tools-and-html-that-loads-nothing.md)). An app is one HTML file, at most 256 KB, that portalr runs for everyone who opens the thread, sandboxed on an origin of its own, loading nothing, beside its `summary` and a label saying an agent made it. Its HTML loads nothing: a script, a module, a stylesheet, an image or a font from anywhere is refused, each named, and goes back to the model to write inline or as a `data:` URL.

An app keeps a `state`, at most 64 KB, which the people using it change through portalr's host, as themselves: a person's edit of an app changes its `state` alone, and its HTML is always an agent's. What it sends with `submit` is a `submission` with `app_id`, which relayr bridges as `ui:app_submitted`. Archiving an app switches that one off; switching `ui:mini-apps` off, for the deployment, a tenant or a workspace, stops every app there.

## Rules

With relayr's `forms` extra, `relayr.ui`, a rule is written once for both ways of asking:

```python
from relayr.events import BRIDGED, Projections
from relayr.ui import UI_EVENTS, UI_PROJECTIONS, UI_PUBLISHERS, FormSubmitted

automation = reflexr.Workspaces(
    storage,
    events=[*BRIDGED, *UI_EVENTS],
    publishers=UI_PUBLISHERS,
    rules=[reflexr.Rule(name="app:lunch", when=reflexr.on(FormSubmitted), then=reflexr.run("book"))],
)
followers = Followers(collaboration, automation, ledger, projections=Projections(**UI_PROJECTIONS))
```

Merge `UI_PROJECTIONS["artifacts"]` and `UI_PROJECTIONS["deferred"]` with the application's own projections of those names when it has any. `UI_PUBLISHERS` reserves `ui:` to relayr's follower, so no client publishes a submission itself.
