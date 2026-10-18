"""The committed OpenAPI document matches relayr's routers."""

import io
import json
import runpy
from contextlib import redirect_stdout
from pathlib import Path

import httpx
import pytest

from lattice_core.refusals import Refused
from relayr.fastapi.openapi import no_credentials, openapi_app, openapi_document

DOCUMENT = Path(__file__).parent.parent / "schemas" / "relayr.openapi.json"


def test_the_committed_document_is_current() -> None:
    assert json.loads(DOCUMENT.read_text()) == openapi_document(), "run `moon run relayr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_document() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("relayr.fastapi.openapi", run_name="__main__")
    assert json.loads(output.getvalue()) == openapi_document()


async def test_the_documents_application_admits_no_one_and_binds_nothing() -> None:
    transport = httpx.ASGITransport(app=openapi_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://relayr") as client:
        read = await client.get("/relayr/v1/workspaces/main/tracker")
        nudged = await client.post("/relayr/v1/trackers/acme/fake", content=b"{}")
    assert read.status_code == 401
    assert Refused.model_validate(read.json()).detail == "unauthorized"
    assert nudged.status_code == 401, "no tenant's credentials verify a nudge"


async def test_the_documents_application_has_no_tenants_credentials() -> None:
    with pytest.raises(LookupError, match="no tenants"):
        await no_credentials("acme")
