import importlib
import os

import pytest

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
