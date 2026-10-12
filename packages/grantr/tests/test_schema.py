"""The committed OpenAPI document matches the router."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import httpx
import pytest

from grantr.fastapi.openapi import openapi_app, openapi_document

DOCUMENT = Path(__file__).parent.parent / "schemas" / "grantr.openapi.json"


def test_the_committed_document_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == openapi_document(), "run `moon run grantr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_document() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("grantr.fastapi.openapi", run_name="__main__")
    assert json.loads(output.getvalue()) == openapi_document()


async def test_the_documents_application_admits_no_caller() -> None:
    transport = httpx.ASGITransport(app=openapi_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://grantr") as client:
        assert (await client.get("/grantr/v1/me")).status_code == 401
