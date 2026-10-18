"""The artifact types' own refusals, and ids derived from what a submission answers."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from artifactr.core import load_artifact
from artifactr.ui import UI_TYPES, submission_id
from artifactr.ui.types import (
    MAX_APP_HTML_BYTES,
    MAX_APP_STATE_BYTES,
    MAX_DASHBOARD_BYTES,
    MAX_SERIES,
    MAX_TABLE_ROWS,
    App,
    Dashboard,
    Form,
    FormRequest,
    Submission,
)

NOW = datetime(2026, 10, 17, tzinfo=UTC)
SCHEMA = {"properties": {"note": {"type": "string"}}}


def test_the_kinds_are_the_rfcs() -> None:
    assert [t.kind for t in UI_TYPES] == ["form", "submission", "dashboard", "app"]


def test_a_form_is_stored_with_its_schema_under_schema() -> None:
    form = Form.model_validate({"title": "Poll", "schema": SCHEMA, "submissions": "per_person"})
    data = form.to_json()
    assert data["schema"] == {
        "type": "object",
        "properties": {"note": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    }
    assert load_artifact("form", data) == form


@pytest.mark.parametrize("model", [Form, FormRequest])
def test_a_forms_hints_must_fit_its_schema(model: Any) -> None:
    ok = {"title": "T", "schema": SCHEMA, "ui": {"fields": {"note": {"widget": "textarea"}}}}
    assert model.model_validate(ok).ui is not None
    with pytest.raises(ValidationError, match="ui names other"):
        model.model_validate({**ok, "ui": {"order": ["other"]}})


@pytest.mark.parametrize(
    "data",
    [
        {"version": 1, "values": {}},
        {"form_id": "f", "app_id": "a", "version": 1, "values": {}},
    ],
)
def test_a_submission_answers_a_form_or_an_app(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="a form or an app, and only one"):
        Submission.model_validate(data)


@pytest.mark.parametrize(
    "form",
    [
        {"title": "x" * 201, "schema": SCHEMA},
        {"title": "T", "schema": SCHEMA, "ui": {"submit_label": "x" * 40_000}},
    ],
)
def test_a_form_is_capped_whole_title_and_hints_with_its_schema(form: dict[str, Any]) -> None:
    for model in (Form, FormRequest):
        with pytest.raises(ValidationError):
            model.model_validate(form)


def _dashboard(*panels: dict[str, Any]) -> Dashboard:
    return Dashboard.model_validate({"title": "Ops", "panels": list(panels), "as_of": NOW})


def test_a_dashboard_holds_every_kind_of_panel() -> None:
    dashboard = _dashboard(
        {"type": "stat", "label": "Open", "value": 12, "unit": "incidents", "change": -3},
        {"type": "stat", "label": "Status", "value": "Green"},
        {
            "type": "bar",
            "label": "By day",
            "index": {"key": "day", "name": "Day"},
            "series": [{"key": "open", "name": "Open"}],
            "rows": [{"day": "Mon", "open": 3}, {"day": "Tue", "open": None}],
        },
        {"type": "donut", "label": "By area", "parts": [{"key": "api", "name": "API", "value": 2}]},
        {
            "type": "table",
            "label": "Latest",
            "columns": [{"key": "id", "name": "Id"}],
            "rows": [{"id": "i1", "paged": True}],
        },
        {"type": "text", "text": "**All** quiet."},
        {"type": "form", "form_id": "form_1"},
    )
    assert [panel.type for panel in dashboard.panels] == [
        "stat",
        "stat",
        "bar",
        "donut",
        "table",
        "text",
        "form",
    ]
    assert load_artifact("dashboard", dashboard.to_json()) == dashboard


@pytest.mark.parametrize(
    "panel",
    [
        {
            "type": "line",
            "label": "Too many",
            "index": {"key": "d", "name": "D"},
            "series": [{"key": f"s{i}", "name": "S"} for i in range(MAX_SERIES + 1)],
            "rows": [],
        },
        {
            "type": "table",
            "label": "Too long",
            "columns": [{"key": "a", "name": "A"}],
            "rows": [{"a": 1}] * (MAX_TABLE_ROWS + 1),
        },
        {"type": "stat", "label": "Not a number", "value": True},
        {
            "type": "donut",
            "label": "Less than none",
            "parts": [{"key": "a", "name": "A", "value": -1}],
        },
        {"type": "stat", "label": "Too large", "value": 2**60},
        {"type": "chart", "label": "No such panel"},
    ],
)
def test_a_panel_over_its_limits_is_refused(panel: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _dashboard(panel)


def test_a_dashboard_is_capped() -> None:
    text = {"type": "text", "text": "x" * (MAX_DASHBOARD_BYTES // 2)}
    with pytest.raises(ValidationError, match=f"over the limit of {MAX_DASHBOARD_BYTES}"):
        _dashboard(text, text)


def test_a_dashboard_is_true_as_of_a_moment_with_its_zone() -> None:
    with pytest.raises(ValidationError):
        Dashboard.model_validate({"title": "Ops", "as_of": "2026-10-17T00:00:00"})


def test_an_apps_summary_is_capped() -> None:
    with pytest.raises(ValidationError):
        App.model_validate({"title": "Calc", "summary": "x" * 2_001, "html": ""})


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"html": "x" * (MAX_APP_HTML_BYTES + 1)}, f"over the limit of {MAX_APP_HTML_BYTES}"),
        (
            {"html": "", "state": {"x": "y" * MAX_APP_STATE_BYTES}},
            f"limit of {MAX_APP_STATE_BYTES}",
        ),
    ],
)
def test_an_app_is_capped(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        App.model_validate({"title": "Calc", "summary": "A calculator", **data})


_DATA_PNG = "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.parametrize(
    "html",
    [
        '<!doctype html><button disabled onclick="go()">Roll</button><script>go()</script>',
        f'<img src="{_DATA_PNG}" srcset="{_DATA_PNG} 1x, {_DATA_PNG} 2x"><a href="#top">Up</a>',
        "<style>body { background: url(data:image/png;base64,AA//) }</style>",
        "<a href='javascript:void(0)' style=\"background: url('#grain')\">Go</a>",
        '<link rel="icon" href="about:blank"><img src="" alt="">',
        "<p>See https://example.com, in words only.</p>",
    ],
)
def test_an_app_loads_only_what_it_holds(html: str) -> None:
    assert App.model_validate({"title": "Dice", "summary": "Rolls dice", "html": html}).html == html


@pytest.mark.parametrize(
    ("html", "named"),
    [
        ('<script src="https://cdn.example/x.js"></script>', "<script src>: https://cdn"),
        ('<link rel="stylesheet" href="//fonts.example/css">', "<link href>: //fonts"),
        ('<img src="cat.png">', "<img src>: cat.png"),
        (f'<img srcset="{_DATA_PNG} 1x, https://e.example/2.png 2x">', "<img srcset>: https://e"),
        ('<a href="/" ping="https://e.example/p">x</a>', "<a href>: /; <a ping>: https://e"),
        ('<form action="https://e.example/f"></form>', "<form action>: https://e"),
        ("<div style=\"background:url( 'https://e.example/b' )\">", "<div style>: https://e"),
        ("<style>@import 'https://e.example/s.css';</style>", "<style>: https://e"),
        ('<style>p { background: image-set("x.png" 1x) }</style>', "<style>: x.png"),
        ('<meta http-equiv="Refresh" content="0;url=https://e">', "<meta http-equiv>: a refresh"),
        ('<object data="https://e.example/o"></object>', "<object data>: https://e"),
        ('<base href="https://e.example/">', "<base href>: https://e"),
    ],
)
def test_an_app_that_loads_from_outside_is_refused_with_what_it_loads(
    html: str, named: str
) -> None:
    with pytest.raises(ValidationError, match="reaches no network") as refused:
        App.model_validate({"title": "Dice", "summary": "Rolls dice", "html": html})
    assert named in str(refused.value)


def test_a_submission_id_takes_a_principal_or_a_nonce_not_both() -> None:
    with pytest.raises(ValueError, match="not both"):
        submission_id("form_1", principal="user:alice", nonce="n")
    assert submission_id("form_1").startswith("sub_")
    assert len(submission_id("form_1")) == 36
