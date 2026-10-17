import importlib
import os

import pytest

from tests.databases import POSTGRES_URL


def pytest_configure(config: pytest.Config) -> None:
    """Register the test artifact and feedback types before any test refers to them by name."""
    importlib.import_module("tests.artifact_types")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Leave out the PostgreSQL tests unless a database is configured, and WordCraft's unless its
    CLI is; the summary counts them."""
    needs = {"postgres": POSTGRES_URL, "wordcraft": os.environ.get("ARTIFACTR_TEST_WORDCRAFT")}
    left_out = [
        item
        for item in items
        if any(item.get_closest_marker(marker) and not given for marker, given in needs.items())
    ]
    if left_out:
        config.hook.pytest_deselected(items=left_out)
        items[:] = [item for item in items if item not in left_out]
