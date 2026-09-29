from importlib.metadata import version

import evalr


def test_version_matches_the_distribution() -> None:
    assert evalr.__version__ == version("evalr")
