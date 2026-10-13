"""Checks on text before it is stored.

PostgreSQL's text can't hold a NUL character, so a storage that may be PostgreSQL refuses one
before anything is stored. :func:`holds_nul` finds one, and the caller raises its own error.
"""

from collections.abc import Collection, Mapping
from typing import cast

from pydantic import BaseModel

__all__ = ["holds_nul"]


def holds_nul(*values: object) -> bool:
    """Whether any string ``values`` hold, as models, mappings or collections, has a NUL character.

    A model is read as its ``model_dump()``, and a mapping's keys are read as well as its values.
    Bytes are not text, and are passed over.
    """
    pending: list[object] = list(values)  # a stack, so deep data can't exhaust recursion
    while pending:
        value = pending.pop()
        found = value.model_dump() if isinstance(value, BaseModel) else value
        if isinstance(found, str):
            if "\x00" in found:
                return True
        elif isinstance(found, Mapping):
            pending += cast("Mapping[object, object]", found).items()
        elif isinstance(found, Collection) and not isinstance(found, bytes):
            pending += cast("Collection[object]", found)
    return False
