import importlib
import os

import pytest

from tests.databases import POSTGRES_URL

# pydantic-ai prints an observability banner when an agent is built; tests have no terminal.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def pytest_configure(config: pytest.Config) -> None:
    """Register the test artifact and feedback types before any test refers to them by name."""
    importlib.import_module("tests.artifact_types")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Leave out the PostgreSQL tests unless a database is configured; the summary counts them."""
    if POSTGRES_URL:
        return
    postgres = [item for item in items if item.get_closest_marker("postgres")]
    config.hook.pytest_deselected(items=postgres)
    items[:] = [item for item in items if item not in postgres]
