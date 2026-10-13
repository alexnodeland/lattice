"""Checks on the text the libraries store.

PostgreSQL's text can't hold a NUL character, so every storage of every library refuses one
alike, before its ``authorize`` hook hears the request (artifactr ADR-0061, reflexr ADR-0060).
Each library raises its own error when :func:`holds_nul` finds one.
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
