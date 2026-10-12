from importlib.metadata import version

import grantr


def test_version_matches_the_distribution() -> None:
    assert grantr.__version__ == version("grantr")
