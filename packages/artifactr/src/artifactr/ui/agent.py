"""The agent's toolset: asking forms, making them, and showing dashboards.

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
the model as a retry that names every field and keyword it refuses. Apps are not offered: making
one is RFC-0005's second phase, which adds its tools (ADR-0078).
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
from artifactr.ui.integrations import DASHBOARDS, FORMS
from artifactr.ui.schema import MAX_CHOICES, MAX_LENGTH, MAX_PROPERTIES
from artifactr.ui.types import Dashboard, Form, FormRequest, Panel, Submissions
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


def ui_tools(
    *, forms: bool = True, dashboards: bool = True, integrations: Integrations | None = None
) -> FunctionToolset[Session[Any]]:
    """Build the toolset: forms' tools, dashboards' tools, or both.

    Args:
        forms: Include ``ask_form``, which pauses the run until a person answers a form, and
            ``create_form``, which makes a form that takes submissions without a run waiting.
            The agent's ``output_type`` must then include ``DeferredToolRequests``.
        dashboards: Include ``show_dashboard`` and ``update_dashboard``.
        integrations: Whether an integration is on in the run's workspace, asked before each
            model request: one that is off has its tools left out of the request, descriptions
            and all. Each integration's default, lattice-core's ``Defaults``, if omitted.
    """
    toolset = FunctionToolset[Session[Any]]()
    panels = json.dumps(TypeAdapter(list[Panel]).json_schema(), separators=(",", ":"))

    asked = integrations or Defaults()
    on_forms, on_dashboards = _offered(FORMS, asked), _offered(DASHBOARDS, asked)

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


def _now() -> str:
    return datetime.now(UTC).isoformat()
