"""The artifact types of forms and dashboards, and ``ask_form``'s request.

Register :data:`UI_TYPES` with the application's own types, in ``Workspaces(types=...)`` and in
``ArtifactWorkspace(types=...)``:

- :class:`Form`, kind ``form``: a :class:`~artifactr.ui.schema.FormSchema` with its hints, and
  how many submissions it takes.
- :class:`Submission`, kind ``submission``: the values a person sent to a form, or to an app,
  against the version they saw. Its id is derived (:func:`~artifactr.ui.ids.submission_id`).
- :class:`Dashboard`, kind ``dashboard``: a snapshot of figures in panels, true ``as_of`` a
  moment, which the agent writes.
- :class:`App`, kind ``app``: a mini app's HTML and its state, which an agent writes through
  its own tools, and which runs sandboxed, loading nothing, where mini apps are on.

Their data's JSON Schema, with ``ask_form``'s request's, is :mod:`artifactr.ui.wire`'s.
"""

import json
from typing import Annotated, Final, Literal, Self, override

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from artifactr.core import Artifact, ArtifactId
from artifactr.ui._common import Number, json_size
from artifactr.ui.schema import MAX_SCHEMA_BYTES, FormSchema, UiHints

__all__ = [
    "AGENT_TYPES",
    "ASK_FORM",
    "MAX_APP_HTML_BYTES",
    "MAX_APP_STATE_BYTES",
    "MAX_DASHBOARD_BYTES",
    "MAX_SERIES",
    "MAX_SUMMARY",
    "MAX_TABLE_ROWS",
    "MAX_TITLE",
    "UI_TYPES",
    "App",
    "ChartPanel",
    "Dashboard",
    "DonutPanel",
    "Form",
    "FormPanel",
    "FormRequest",
    "Key",
    "Panel",
    "Part",
    "StatPanel",
    "Submission",
    "Submissions",
    "TablePanel",
    "TextPanel",
]

MAX_SERIES: Final = 3
"""The most series a bar or line chart holds: as many as portalr's charts have inks for."""

MAX_TABLE_ROWS: Final = 500
"""The most rows a table panel holds."""

MAX_DASHBOARD_BYTES: Final = 256 * 1024
"""The largest dashboard, in the UTF-8 bytes of its compact JSON: every version is
in the log, and relayr bridges each."""

MAX_APP_HTML_BYTES: Final = 256 * 1024
"""The largest app's HTML, in UTF-8 bytes."""

MAX_APP_STATE_BYTES: Final = 64 * 1024
"""The largest app's state, in the UTF-8 bytes of its compact JSON."""

MAX_TITLE: Final = 200
"""The longest title of a form, a dashboard or an app, in characters."""

MAX_SUMMARY: Final = 2_000
"""The longest summary of an app, its text in place of what it runs, in characters."""

ASK_FORM: Final = "ask_form"
"""The tool name of a paused request that asks a form, which portalr renders as one."""

Submissions = Literal["once", "per_person", "many"]
"""How many submissions a form takes: one in all, one a person, or any number."""

_Title = Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]


def _form_fits(title: str, schema: FormSchema, ui: UiHints | None) -> None:
    """Hints that fit the schema, and a form within its limit, as it is stored."""
    if ui is not None:
        ui.check(schema)
    stored: dict[str, JsonValue] = {"title": title, "schema": schema.model_dump(mode="json")}
    if ui is not None:
        stored["ui"] = ui.model_dump(mode="json")
    if (size := json_size(stored)) > MAX_SCHEMA_BYTES:
        raise ValueError(f"the form is {size} bytes, over the limit of {MAX_SCHEMA_BYTES}")


class FormRequest(BaseModel):
    """What ``ask_form`` asks: the arguments its paused request carries, as portalr reads them.

    The request's ``args`` hold these as the model called the tool; the tool checked them before
    the run paused, and the answer is checked against ``schema``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", serialize_by_alias=True)

    title: _Title
    form_schema: FormSchema = Field(alias="schema")
    ui: UiHints | None = None

    @model_validator(mode="after")
    def _fits(self) -> Self:
        _form_fits(self.title, self.form_schema, self.ui)
        return self


class Form(Artifact, name="form"):
    """A form that takes submissions without a run waiting.

    It is for a poll, a sign-up, or a form that outlives its run. A submission names the version
    it was made against; an edit of the form makes a new one, so a submission made against an
    earlier one is refused as changed. Only its author, or whom the application's ``is_admin``
    allows, changes its ``schema`` or ``closed``.
    """

    model_config = ConfigDict(serialize_by_alias=True)

    title: _Title
    form_schema: FormSchema = Field(alias="schema")
    ui: UiHints | None = None
    submissions: Submissions = "once"
    closed: bool = False

    @model_validator(mode="after")
    def _fits(self) -> Self:
        _form_fits(self.title, self.form_schema, self.ui)
        return self


class Submission(Artifact, name="submission"):
    """The values a person sent to a form, or to an app, against the version they saw.

    It answers one of the two, ``form_id`` or ``app_id``. A ``many`` form's and an app's carry
    the ``nonce`` their id is derived from. People never edit one.
    """

    form_id: ArtifactId | None = None
    app_id: ArtifactId | None = None
    version: int = Field(ge=1)
    values: dict[str, JsonValue]
    nonce: Annotated[str, Field(min_length=1)] | None = None

    @model_validator(mode="after")
    def _answers_one(self) -> Self:
        if (self.form_id is None) == (self.app_id is None):
            raise ValueError("a submission answers a form or an app, and only one")
        return self


# ─── dashboards ───────────────────────────────────────────────────────────────


class _Panel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Key(_Panel):
    """A key in a chart's rows or a table's, and the name it is shown by."""

    key: Annotated[str, Field(min_length=1)]
    name: str


def _not_negative(value: float) -> float:
    if value < 0:
        raise ValueError("a part is never negative")
    return value


class Part(Key):
    """One part of a whole, in a donut."""

    value: Annotated[Number, AfterValidator(_not_negative)]


class StatPanel(_Panel):
    """One figure: its label, its value, its unit, and how much it changed."""

    type: Literal["stat"]
    label: str
    value: Number | str
    unit: str | None = None
    change: Number | None = None


class ChartPanel(_Panel):
    """A bar or line chart: rows indexed by ``index``, and up to :data:`MAX_SERIES` series."""

    type: Literal["bar", "line"]
    label: str
    index: Key
    series: Annotated[list[Key], Field(min_length=1, max_length=MAX_SERIES)]
    rows: list[dict[str, str | Number | None]]


class DonutPanel(_Panel):
    """A whole in parts: the largest three in the chart's inks, the rest folded into "Other"."""

    type: Literal["donut"]
    label: str
    parts: Annotated[list[Part], Field(min_length=1)]


class TablePanel(_Panel):
    """A table: its columns, and up to :data:`MAX_TABLE_ROWS` rows keyed by them."""

    type: Literal["table"]
    label: str
    columns: Annotated[list[Key], Field(min_length=1)]
    rows: Annotated[list[dict[str, str | Number | bool | None]], Field(max_length=MAX_TABLE_ROWS)]


class TextPanel(_Panel):
    """Markdown, which portalr renders without raw HTML."""

    type: Literal["text"]
    text: str


class FormPanel(_Panel):
    """A form artifact, by its id, shown to submit in place: a form with no fields is a button."""

    type: Literal["form"]
    form_id: ArtifactId


Panel = Annotated[
    StatPanel | ChartPanel | DonutPanel | TablePanel | TextPanel | FormPanel,
    Field(discriminator="type"),
]
"""One panel of a dashboard, told apart by its ``type``."""


class Dashboard(Artifact, name="dashboard"):
    """A snapshot of figures in panels, which the agent writes, true ``as_of`` a moment.

    Each update is a new version; a dashboard is at most :data:`MAX_DASHBOARD_BYTES`.
    """

    title: _Title
    panels: list[Panel] = Field(default_factory=list[Panel])
    as_of: AwareDatetime

    @model_validator(mode="after")
    def _fits(self) -> Self:
        if (size := json_size(self.to_json())) > MAX_DASHBOARD_BYTES:
            raise ValueError(
                f"the dashboard is {size} bytes, over the limit of {MAX_DASHBOARD_BYTES}"
            )
        return self


# ─── apps ─────────────────────────────────────────────────────────────────────


class App(Artifact, name="app"):
    """A mini app: one HTML file an agent wrote, its text fallback, and its state.

    portalr runs it sandboxed, on an origin of its own, loading nothing, while mini apps are on
    in the workspace; its ``summary`` is shown beside it, and in its place where it doesn't run.
    An agent writes it, and its HTML names nothing to load, which the agent's tools and the
    checks hold; a person changes only its ``state``, through the app.
    """

    title: _Title
    summary: Annotated[str, Field(max_length=MAX_SUMMARY)]
    html: str
    state: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])

    @override
    def render_for_tool(self) -> str:
        """Return the app without its HTML, which ``read_app`` gives the agent.

        Only an agent writes an app's HTML, and a page of markup can match the gateway's
        ``prompt-injection`` word lists; a ``read_artifact`` result that held it would stay in the
        thread's history and block every later request. ``read_app``'s result is one the gateway
        leaves unscanned, as it does the model's own tool arguments (ADR-0098).
        """
        state = json.dumps(self.state, sort_keys=True) if self.state else "{}"
        return (
            f"{self.title}\n\n{self.summary}\n\nIts state: {state}\n\n"
            "Its HTML isn't shown here: read it with read_app to change it."
        )

    @model_validator(mode="after")
    def _fits(self) -> Self:
        if (size := len(self.html.encode())) > MAX_APP_HTML_BYTES:
            raise ValueError(f"the HTML is {size} bytes, over the limit of {MAX_APP_HTML_BYTES}")
        if (size := json_size(self.state)) > MAX_APP_STATE_BYTES:
            raise ValueError(f"the state is {size} bytes, over the limit of {MAX_APP_STATE_BYTES}")
        return self


UI_TYPES: Final[tuple[type[Artifact], ...]] = (Form, Submission, Dashboard, App)
"""The forms layer's artifact types, for ``Workspaces(types=...)``."""

AGENT_TYPES: Final[tuple[type[Artifact], ...]] = (Form, Dashboard)
"""The types an agent makes and changes with ``ArtifactWorkspace``'s generic tools, for its
``types=...``: not a submission, which is a person's, nor an app, which ``create_app`` and
``update_app`` make and change, while mini apps are on."""
