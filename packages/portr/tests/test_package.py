"""portr's package: its version is the distribution's."""

from importlib.metadata import version

import portr


def test_version_matches_the_distribution() -> None:
    assert portr.__version__ == version("portr-ai")
