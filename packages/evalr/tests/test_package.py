from importlib.metadata import version
from typing import TypeAliasType

import evalr
import evalr.core


def test_version_matches_the_distribution() -> None:
    assert evalr.__version__ == version("evalr")


def test_every_type_in_the_core_is_top_level() -> None:
    core = {name: getattr(evalr.core, name) for name in evalr.core.__all__}
    types = {name for name, o in core.items() if isinstance(o, type | TypeAliasType)}
    assert types - set(evalr.__all__) == set()
