import functools
import importlib
import os
from collections.abc import Callable, Iterator
from typing import Concatenate

import pytest
from starlette.testclient import TestClient

from tests.clients import OPEN
from tests.databases import POSTGRES_URL


def pytest_configure(config: pytest.Config) -> None:
    """Register the test artifact and feedback types before any test refers to them by name."""
    importlib.import_module("tests.artifact_types")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Leave out the PostgreSQL tests unless a database is configured, and a crafting app's
    unless its CLI is; the summary counts them."""
    given = os.environ.get("ARTIFACTR_TEST_CRAFT_CLI")
    running = os.environ.get("ARTIFACTR_TEST_CRAFT") if given else None

    def unready(item: pytest.Item) -> bool:
        craft = item.get_closest_marker("craft")
        return bool(
            (item.get_closest_marker("postgres") and not POSTGRES_URL)
            or (craft and (craft.args or (None,))[0] != running)
        )

    left_out = [item for item in items if unready(item)]
    if left_out:
        config.hook.pytest_deselected(items=left_out)
        items[:] = [item for item in items if item not in left_out]


@pytest.fixture(autouse=True)
def _clients_entered(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Refuse a request through a `TestClient` that isn't entered, and leave the ones entered.

    Unentered, each request has an event loop of its own (see `tests/clients.py`).
    """
    # `send` is what `request`, `get` and the rest, and `stream`, all go through.
    for name in ("send", "websocket_connect"):
        monkeypatch.setattr(TestClient, name, _only_entered(getattr(TestClient, name)))
    try:
        yield
    finally:
        OPEN.close()


def _only_entered[**P, R](
    method: Callable[Concatenate[TestClient, P], R],
) -> Callable[Concatenate[TestClient, P], R]:
    """The client's method, refused unless the client is entered."""

    @functools.wraps(method)
    def checked(client: TestClient, *args: P.args, **kwargs: P.kwargs) -> R:
        assert client.portal is not None, "enter the TestClient: tests.clients.entered(app)"
        return method(client, *args, **kwargs)

    return checked
