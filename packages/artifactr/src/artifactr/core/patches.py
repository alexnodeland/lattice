"""Patches: the two ways artifact data changes.

- :class:`JsonPatch` is RFC 6902 JSON Patch over the artifact's JSON data. Any artifact type
  accepts it.
- :class:`TextEdits` replaces exact, unique strings in one text field. It is the edit form
  language models perform most reliably, and it rebases well onto newer versions.

Patch kinds are fixed by the library (ADR-0003); artifact types cannot define their own.
"""

from typing import Annotated, Any, Literal, cast

import jsonpatch
import jsonpointer
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from artifactr.core.errors import PatchFailed

_PREVIEW = 60
_MAX_DESCRIBED_OPS = 3


class JsonPatch(BaseModel):
    """An RFC 6902 JSON Patch."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["json_patch"] = "json_patch"
    ops: tuple[dict[str, JsonValue], ...]


class TextEdit(BaseModel):
    """Replace one exact occurrence of ``old`` with ``new``."""

    model_config = ConfigDict(frozen=True)

    old: str
    new: str


class TextEdits(BaseModel):
    """A sequence of anchored replacements in one text field.

    Each ``old`` must occur exactly once in the field at the moment it is applied. An empty
    ``old`` is allowed only when the field is empty, to write its first content.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["text_edits"] = "text_edits"
    field: str = "text"
    edits: tuple[TextEdit, ...] = Field(min_length=1)


Patch = Annotated[JsonPatch | TextEdits, Field(discriminator="kind")]
"""Any patch, discriminated by ``kind``."""


def apply_patch(data: dict[str, JsonValue], patch: Patch) -> dict[str, JsonValue]:
    """Apply a patch to JSON data, returning new data.

    Args:
        data: The artifact's current JSON data. It is not modified.
        patch: The patch to apply.

    Returns:
        The patched data.

    Raises:
        PatchFailed: If the patch does not apply.
    """
    if isinstance(patch, JsonPatch):
        try:
            result: Any = jsonpatch.apply_patch(data, patch.ops)
        except (jsonpatch.JsonPatchException, jsonpointer.JsonPointerException) as error:
            raise PatchFailed(f"the JSON patch does not apply: {error}") from error
        return cast("dict[str, JsonValue]", result)
    text = data.get(patch.field)
    if not isinstance(text, str):
        raise PatchFailed(f"{patch.field!r} is not a text field")
    for edit in patch.edits:
        text = _replace_once(text, edit)
    return {**data, patch.field: text}


def _replace_once(text: str, edit: TextEdit) -> str:
    if not edit.old:
        if text:
            raise PatchFailed("an empty anchor is only allowed when the text is empty")
        return edit.new
    count = text.count(edit.old)
    if count != 1:
        problem = "not found" if count == 0 else f"ambiguous: it occurs {count} times"
        raise PatchFailed(f"the anchor {_preview(edit.old)} is {problem}")
    return text.replace(edit.old, edit.new, 1)


def diff(old: dict[str, JsonValue], new: dict[str, JsonValue]) -> JsonPatch:
    """Return the JSON Patch that turns ``old`` into ``new``."""
    return JsonPatch(ops=tuple(jsonpatch.make_patch(old, new).patch))


def describe_patch(patch: Patch) -> str:
    """Return a short, human-readable description of a patch.

    Used as the change summary when neither the command nor the artifact type provides one.
    """
    if isinstance(patch, TextEdits):
        count = len(patch.edits)
        return f"edited {patch.field} ({count} replacement{'s' if count != 1 else ''})"
    shown = [f"{op.get('op')} {op.get('path')}" for op in patch.ops[:_MAX_DESCRIBED_OPS]]
    hidden = len(patch.ops) - len(shown)
    if hidden:
        shown.append(f"and {hidden} more")
    return "; ".join(shown)


def _preview(text: str) -> str:
    return repr(text if len(text) <= _PREVIEW else text[: _PREVIEW - 1] + "…")
