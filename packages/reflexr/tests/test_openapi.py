"""The committed OpenAPI document matches the router."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import httpx
import pytest

from reflexr.fastapi.openapi import openapi_app, openapi_document
from reflexr.fastapi.router import Refused

DOCUMENT = Path(__file__).parent.parent / "schemas" / "reflexr.openapi.json"


def test_the_committed_document_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == openapi_document(), "run `moon run reflexr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_document() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("reflexr.fastapi.openapi", run_name="__main__")
    assert json.loads(output.getvalue()) == openapi_document()


async def test_the_documents_application_admits_no_one() -> None:
    transport = httpx.ASGITransport(app=openapi_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://reflexr") as client:
        assert (await client.get("/workspaces/main/runs/run_1")).status_code == 401


def test_every_tag_is_required() -> None:
    """A union member's tag is required (ADR-0060). A REST body is always a command frame, so
    its own ``type`` may be left out."""
    schemas = openapi_document()["components"]["schemas"]
    for name, schema in schemas.items():
        if name == "CommandFrame":
            continue
        tags = {key for key, field in schema.get("properties", {}).items() if "const" in field}
        assert tags <= set(schema.get("required", [])), name


async def test_a_refused_request_answers_as_the_document_says() -> None:
    transport = httpx.ASGITransport(app=openapi_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://reflexr") as client:
        refused = await client.get("/workspaces/main/runs/run_1")
    assert Refused.model_validate(refused.json()).detail == "unauthorized"
