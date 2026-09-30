from importlib.metadata import version

import artifactr


def test_version_matches_distribution_metadata() -> None:
    assert artifactr.__version__ == version("artifactr-ai")
