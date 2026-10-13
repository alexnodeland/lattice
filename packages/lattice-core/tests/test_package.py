"""The package's version is its distribution's."""

from importlib.metadata import version

import lattice_core


def test_the_version_is_the_distributions() -> None:
    assert lattice_core.__version__ == version("lattice-core-ai")
