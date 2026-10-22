"""Over REST: a version that doesn't grow is refused, and off is a conflict that leaves reads."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent

from artifactr.agent import Runner, Session
from artifactr.excalidraw import (
    EXCALIDRAW,
    EXCALIDRAW_TYPES,
    excalidraw_checks,
    excalidraw_key_of,
)
from artifactr.fastapi import artifactr_router
from artifactr.workspace import InMemoryStorage, Workspaces, integration_gate
from tests.agent.conftest import Script
from tests.excalidraw.scenes import data, element
from tests.fastapi.conftest import Latch, command, resolve_actor
from tests.ui.toggles import Toggles

BASE = "/v1/workspaces/w1"


@pytest.fixture
def toggles() -> Toggles:
    return Toggles()


@pytest.fixture
def client(toggles: Toggles) -> Iterator[TestClient]:
    agent: Agent[Session[Latch], Any] = Agent(Script().model, deps_type=Session[Latch])
    workspaces = Workspaces(
        InMemoryStorage(),
        types=EXCALIDRAW_TYPES,
        checks=excalidraw_checks(),
        gate=integration_gate(toggles, excalidraw_key_of),
    )
    app = FastAPI()
    app.include_router(
        artifactr_router(workspaces, Runner(agent, app=Latch()), resolve_actor=resolve_actor),
        prefix="/v1",
    )
    with TestClient(app) as client:
        yield client


def _create(client: TestClient) -> None:
    made = command(
        "c1",
        type="create_artifact",
        artifact_id="d1",
        kind="excalidraw_diagram",
        data=data(element("r1")),
    )
    assert client.post(f"{BASE}/commands", json=made).status_code == 200


def _move(command_id: str, version: int) -> dict[str, Any]:
    moved = element("r1", version=version, x=40).model_dump(mode="json")
    ops = [
        {"op": "test", "path": "/elements/r1/version", "value": 1},
        {"op": "replace", "path": "/elements/r1", "value": moved},
    ]
    return command(
        command_id,
        type="edit_artifact",
        artifact_id="d1",
        base_version=1,
        patch={"kind": "json_patch", "ops": ops},
    )


def test_a_version_that_doesnt_grow_is_refused_over_rest(client: TestClient) -> None:
    _create(client)
    refused = client.post(f"{BASE}/commands", json=_move("c2", version=1))
    assert refused.status_code == 422
    assert refused.json()["rejection"]["type"] == "validation_failed"
    assert "version must grow" in refused.json()["rejection"]["message"]
    assert client.post(f"{BASE}/commands", json=_move("c3", version=2)).status_code == 200


def test_off_is_a_conflict_and_the_diagram_still_reads(
    client: TestClient, toggles: Toggles
) -> None:
    _create(client)
    toggles.off["w1"] = {EXCALIDRAW}
    refused = client.post(f"{BASE}/commands", json=_move("c2", version=2))
    assert refused.status_code == 409
    assert refused.json()["rejection"]["integration"] == "excalidraw"
    read = client.get(f"{BASE}/artifacts/d1")
    assert read.status_code == 200
    assert read.json()["data"]["elements"]["r1"]["versionNonce"] == 10
