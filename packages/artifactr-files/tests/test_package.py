from importlib.metadata import version

import artifactr_files


def test_version_matches_the_distribution() -> None:
    assert artifactr_files.__version__ == version("artifactr-files-ai")
