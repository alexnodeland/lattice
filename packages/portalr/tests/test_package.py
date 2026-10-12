from importlib.metadata import version

import portalr


def test_version_matches_the_distribution() -> None:
    assert portalr.__version__ == version("portalr")
