import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Leave out the acceptance tests unless the stack's tools run; the summary counts them."""
    if os.environ.get("PORTALR_TEMPO_URL"):
        return
    acceptance = [item for item in items if item.get_closest_marker("acceptance")]
    config.hook.pytest_deselected(items=acceptance)
    items[:] = [item for item in items if item not in acceptance]
