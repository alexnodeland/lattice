"""The agent's toolset: asking forms, making them, showing dashboards, and making mini apps.

Register :func:`ui_tools` on the agent as an application toolset (ADR-0017), beside
the ``ArtifactWorkspace`` capability with :data:`~artifactr.ui.types.AGENT_TYPES` among its
types, the kinds an agent makes and changes itself::

    agent = Agent(
        model,
        deps_type=Session[None],
        output_type=[str, DeferredToolRequests],
        toolsets=[ui_tools()],
        capabilities=[ArtifactWorkspace(types=[*app_types, *AGENT_TYPES])],
    )

Each tool checks what the model wrote before anything is recorded, and gives a refusal back to
the model as a retry that names every field and keyword it refuses. Each is offered only while
its integration is on in the run's workspace: mini apps', off by default, among them (ADR-0082).
"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_ai import CallDeferred, FunctionToolset, ModelRetry, RunContext, ToolDefinition

from artifactr.agent import Session, describe_outcome
from artifactr.core import CreateArtifact, EditArtifact, diff
from artifactr.ui._common import MAX_NUMBER, refusal
from artifactr.ui._html import refused
from artifactr.ui.integrations import DASHBOARDS, FORMS, MINI_APPS
from artifactr.ui.schema import MAX_CHOICES, MAX_LENGTH, MAX_PROPERTIES
from artifactr.ui.types import (
    MAX_APP_HTML_BYTES,
    MAX_APP_STATE_BYTES,
    App,
    Dashboard,
    Form,
    FormRequest,
    Panel,
    Submissions,
)
from lattice_core.integrations import Defaults, Integrations

__all__ = ["ui_tools"]

_SUBSET = f"""\
The schema is a JSON Schema object in a subset: `type: "object"`, `title`, `description`, \
`properties` and `required` at the root. Each property has a `title` and a `description`, and \
is one of: a `string`, with `minLength`, `maxLength` (at most {MAX_LENGTH}), a `format` of \
`date`, `date-time`, `email` or `uri` (http, https or mailto), and a `default`; choices, \
`{{"type": "string", "enum": [...]}}` or \
`{{"type": "string", "oneOf": [{{"const": ..., "title": ...}}]}}`, with a `default`; a `number` or \
an `integer`, with `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` \
and a `default`; a `boolean`, with a `default`; or an `array` of choices, with `items` as \
choices, `uniqueItems`, `minItems`, `maxItems` and a `default`. Nothing else: no `$ref`, \
nested objects, `pattern`, `allOf`, `anyOf`, `not` or `if`, and never a password. At most \
{MAX_PROPERTIES} properties, named as identifiers, {MAX_CHOICES} choices each, and numbers \
within ±{MAX_NUMBER}. A form with no properties is a button.

The ui hints are optional: `fields` maps a property to its `widget` (`textarea` for a string, \
`select` for choices, `checkbox` for a boolean), `placeholder` and `help`; `order` lists the \
properties in order; `sections` are `{{"title": ..., "properties": [...]}}`; `submit_label` names \
the button."""

_APP = f"""\
The app is one HTML file, at most {MAX_APP_HTML_BYTES // 1024} KB, run sandboxed for everyone \
who opens the thread, with no network: it loads nothing, so its scripts and styles are inline, \
and its images and fonts `data:` URLs. Its `summary` says in words what it does: it is shown \
beside the app, and in its place wherever apps don't run.

It talks to its host in JSON-RPC 2.0, sending with `window.parent.postMessage(message, "*")` \
and hearing the answers as `message` events. It asks `ui/initialize` first, then sends the \
notification `ui/notifications/initialized`; the result's `hostContext` has `theme` (`light` \
or `dark`) and `styles.variables`, the host's colours as CSS variables, which \
`ui/notifications/host-context-changed` sends again when they change. It calls \
its tools with `tools/call`, `{{"name": ..., "arguments": {{...}}}}`, each answering with \
`structuredContent`: `get_state`, its `state` and `version`; `set_state`, with `patch`, a JSON \
Patch on its state, at most {MAX_APP_STATE_BYTES // 1024} KB, kept as the person's and saved at \
most once every 5 seconds; and `submit`, with `values`, an object sent as the person's \
submission once they confirm it. `ui/open-link`, with a `url`, opens it once the person \
confirms; `ui/notifications/size-changed`, with a `height`, sizes its frame. It has 60 calls \
a minute, each message counted; past them, the host stops answering it."""


def ui_tools(
    *,
    forms: bool = True,
    dashboards: bool = True,
    apps: bool = True,
    integrations: Integrations | None = None,
) -> FunctionToolset[Session[Any]]:
    """Build the toolset: forms' tools, dashboards' tools, mini apps' tools, or any of them.

    Args:
        forms: Include ``ask_form``, which pauses the run until a person answers a form, and
            ``create_form``, which makes a form that takes submissions without a run waiting.
            The agent's ``output_type`` must then include ``DeferredToolRequests``.
        dashboards: Include ``show_dashboard`` and ``update_dashboard``.
        apps: Include ``create_app`` and ``update_app``, offered only while ``ui:mini-apps``,
            off by default, is on in the run's workspace.
        integrations: Whether an integration is on in the run's workspace, asked before each
            model request: one that is off has its tools left out of the request, descriptions
            and all. Each integration's default, lattice-core's ``Defaults``, if omitted.
    """
    toolset = FunctionToolset[Session[Any]]()
    panels = json.dumps(TypeAdapter(list[Panel]).json_schema(), separators=(",", ":"))

    asked = integrations or Defaults()
    on_forms, on_dashboards = _offered(FORMS, asked), _offered(DASHBOARDS, asked)
    on_apps = _offered(MINI_APPS, asked)

    if forms:

        @toolset.tool_plain(
            prepare=on_forms,
            description="Ask the people in this thread to fill in a form, and wait for their "
            f"answer: its values, checked against the schema.\n\n{_SUBSET}",
        )
        async def ask_form(
            title: str, schema: dict[str, Any], ui: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            _checked(FormRequest, {"title": title, "schema": schema, "ui": ui})
            raise CallDeferred

        @toolset.tool(
            prepare=on_forms,
            description="Make a form in this thread that takes submissions without you waiting, "
            "for a poll, a sign-up or a form that outlives this run. `submissions` is `once` (one "
            "in all), `per_person` (one a person) or `many`. Each submission is an artifact of "
            f"kind `submission` with the form's id in its `form_id`.\n\n{_SUBSET}",
        )
        async def create_form(
            ctx: RunContext[Session[Any]],
            title: str,
            schema: dict[str, Any],
            ui: dict[str, Any] | None = None,
            submissions: Submissions = "once",
        ) -> str:
            form = _checked(
                Form, {"title": title, "schema": schema, "ui": ui, "submissions": submissions}
            )
            command = CreateArtifact(
                kind=form.kind, data=form.to_json(), thread_id=ctx.deps.thread_id
            )
            return describe_outcome(await ctx.deps.workspace.commit(command))

    if dashboards:

        @toolset.tool(
            prepare=on_dashboards,
            description="Show figures as a dashboard in this thread: a snapshot, true as of now. "
            f"`panels` is a list of panels, each matching this JSON Schema:\n{panels}",
        )
        async def show_dashboard(
            ctx: RunContext[Session[Any]], title: str, panels: list[dict[str, Any]]
        ) -> str:
            dashboard = _checked(Dashboard, {"title": title, "panels": panels, "as_of": _now()})
            command = CreateArtifact(
                kind=dashboard.kind, data=dashboard.to_json(), thread_id=ctx.deps.thread_id
            )
            return describe_outcome(await ctx.deps.workspace.commit(command))

        @toolset.tool(
            prepare=on_dashboards,
            description="Replace a dashboard's panels with new figures, true as of now, as its "
            "next version. `panels` is as for show_dashboard.",
        )
        async def update_dashboard(
            ctx: RunContext[Session[Any]], id: str, panels: list[dict[str, Any]]
        ) -> str:
            workspace = ctx.deps.workspace
            current = await workspace.get(Dashboard, id)
            data = {**current.data.to_json(), "panels": panels, "as_of": _now()}
            dashboard = _checked(Dashboard, data)
            command = EditArtifact(
                artifact_id=current.id,
                base_version=current.version,
                patch=diff(current.data.to_json(), dashboard.to_json()),
                thread_id=ctx.deps.thread_id,
            )
            return describe_outcome(await workspace.commit(command))

    if apps:

        @toolset.tool(
            prepare=on_apps,
            description="Make a mini app in this thread, for what a form or a dashboard can't "
            f"do, such as a calculator, a layout to arrange or a small game.\n\n{_APP}",
        )
        async def create_app(
            ctx: RunContext[Session[Any]], title: str, summary: str, html: str
        ) -> str:
            app = _app({"title": title, "summary": summary, "html": html})
            command = CreateArtifact(
                kind=app.kind, data=app.to_json(), thread_id=ctx.deps.thread_id
            )
            return describe_outcome(await ctx.deps.workspace.commit(command))

        @toolset.tool(
            prepare=on_apps,
            description="Replace a mini app's HTML, and its summary if it says something else "
            "now, as its next version. Its state is kept. The HTML is as for create_app.",
        )
        async def update_app(
            ctx: RunContext[Session[Any]], id: str, html: str, summary: str | None = None
        ) -> str:
            workspace = ctx.deps.workspace
            current = await workspace.get(App, id)
            data = current.data.to_json()
            changed = {"html": html, **({} if summary is None else {"summary": summary})}
            app = _app({**data, **changed})
            command = EditArtifact(
                artifact_id=current.id,
                base_version=current.version,
                patch=diff(data, app.to_json()),
                thread_id=ctx.deps.thread_id,
            )
            return describe_outcome(await workspace.commit(command))

    return toolset


type _Prepare = Callable[
    [RunContext[Session[Any]], ToolDefinition], Awaitable[ToolDefinition | None]
]


def _offered(key: str, integrations: Integrations) -> _Prepare:
    """Offer an integration's tool only while it runs in the run's workspace."""

    async def prepare(ctx: RunContext[Session[Any]], tool: ToolDefinition) -> ToolDefinition | None:
        workspace = ctx.deps.workspace
        on = await integrations.is_enabled(workspace.tenant_id, workspace.workspace_id, key)
        return tool if on else None

    return prepare


def _checked[M: BaseModel](model: type[M], data: dict[str, Any]) -> M:
    """Validate what the model wrote, or give it back every refusal to retry with."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise ModelRetry(refusal("Refused, fix and retry", error).message) from error


def _app(data: dict[str, Any]) -> App:
    """An app the model wrote, within its limits and loading nothing, or a retry saying why."""
    app = _checked(App, data)
    if (why := refused(app.html)) is not None:
        raise ModelRetry(f"Refused, fix and retry: {why}")
    return app


def _now() -> str:
    return datetime.now(UTC).isoformat()
