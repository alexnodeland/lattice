from importlib.metadata import version

import relayr


def test_version_matches_the_distribution() -> None:
    assert relayr.__version__ == version("relayr-ai")
