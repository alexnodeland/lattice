"""The committed OpenAPI document matches the router: ``moon run portalr:schema`` rewrites it."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import httpx
import pytest

from portalr.fastapi.openapi import openapi_app, openapi_document

DOCUMENT = Path(__file__).parent.parent / "schemas" / "portalr.openapi.json"


def test_the_committed_document_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == openapi_document(), "run `moon run portalr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_document() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("portalr.fastapi.openapi", run_name="__main__")
    assert json.loads(output.getvalue()) == openapi_document()


async def test_the_documents_application_admits_no_caller() -> None:
    transport = httpx.ASGITransport(app=openapi_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://portalr") as client:
        response = await client.get("/portalr/v1/spend", headers={"x-tenant": "acme"})
    assert response.status_code == 401
