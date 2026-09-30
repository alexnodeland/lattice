"""Minimal type stubs for the parts of jsonpatch that artifactr uses."""

from collections.abc import Mapping, Sequence
from typing import Any

class JsonPatchException(Exception): ...

class JsonPatch:
    patch: list[dict[str, Any]]

def apply_patch(
    doc: Mapping[str, Any], patch: Sequence[Mapping[str, Any]], in_place: bool = False
) -> Any: ...
def make_patch(src: Mapping[str, Any], dst: Mapping[str, Any]) -> JsonPatch: ...
