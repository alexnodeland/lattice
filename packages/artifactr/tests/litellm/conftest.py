"""The telemetry recorder, for the gateway's tests."""

from collections.abc import Iterator

import pytest

from tests.telemetry.conftest import Recorder, recording


@pytest.fixture
def recorder() -> Iterator[Recorder]:
    yield from recording()
