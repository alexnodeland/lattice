"""The committed OpenAPI document matches the router."""

import io
import json
import runpy
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import httpx
import pytest

from artifactr.fastapi.openapi import openapi_app, openapi_document
from artifactr.fastapi.router import Refused

SCHEMAS = Path(__file__).parent.parent / "schemas"
DOCUMENT = SCHEMAS / "artifactr.openapi.json"


def test_the_committed_document_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == openapi_document(), "run `moon run artifactr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_document() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("artifactr.fastapi.openapi", run_name="__main__")
    assert json.loads(output.getvalue()) == openapi_document()


async def test_the_documents_application_admits_no_one() -> None:
    transport = httpx.ASGITransport(app=openapi_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://artifactr") as client:
        assert (await client.get("/workspaces/main/runs/run_1")).status_code == 401


def _schemas(node: object) -> Iterator[dict[str, Any]]:
    """Every object schema in a JSON Schema or an OpenAPI document, however deep."""
    if isinstance(node, dict):
        if "properties" in node:
            yield node
        for value in node.values():
            yield from _schemas(value)
    elif isinstance(node, list):
        for value in node:
            yield from _schemas(value)


@pytest.mark.parametrize(
    "document", ["openapi", *sorted(p.name for p in SCHEMAS.glob("*.v1.json"))]
)
def test_every_tag_is_required(document: str) -> None:
    """A field fixed to one value, a union member's tag, is required (ADR-0063)."""
    found = (
        openapi_document()
        if document == "openapi"
        else json.loads((SCHEMAS / document).read_text())
    )
    for schema in _schemas(found):
        tags = {key for key, field in schema["properties"].items() if "const" in field}
        assert tags <= set(schema.get("required", [])), schema.get("title")


async def test_a_refused_request_answers_as_the_document_says() -> None:
    transport = httpx.ASGITransport(app=openapi_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://artifactr") as client:
        refused = await client.get("/workspaces/main/runs/run_1")
    assert Refused.model_validate(refused.json()).detail == "unauthorized"
