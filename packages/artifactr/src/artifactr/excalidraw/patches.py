"""A diagram's edits: JSON Patch scoped to the elements it touches (lattice RFC-0006).

Every writer, person or agent, sends one shape, built here from a diff of the base and the new
elements: each changed element is replaced whole, after a ``test`` of the version it had, a new
one is an ``add``, and a new image is an ``add`` under its digest. Concurrent edits to different
elements never conflict, and nothing is locked:

- **A stale direct edit** fails on its ``base_version``, as ``version_conflict``. Its writer
  rebases: :func:`rebase` reconciles its elements with the head, as Excalidraw's
  ``reconcileElements`` does, and :func:`element_patch` diffs the result against the head.
- **A proposal** is applied to the head when it is accepted; its tests fail it whole, as
  ``patch_failed``, if an element it changes has moved since, and it applies if those it
  changes haven't.
"""

import secrets
from collections.abc import Mapping
from typing import Final

from pydantic import JsonValue

from artifactr.core import JsonPatch
from artifactr.excalidraw.types import Diagram, DiagramFile, Element

__all__ = ["MAX_NONCE", "element_patch", "rebase", "reconcile", "won"]

MAX_NONCE: Final = 2**31 - 1
"""The largest nonce Excalidraw makes: a random 31-bit integer."""


def element_patch(
    base: Diagram,
    elements: Mapping[str, Element],
    files: Mapping[str, DiagramFile] | None = None,
) -> JsonPatch:
    """The patch that takes ``base`` to ``elements``, and adds ``files`` it doesn't have.

    An element that differs is replaced after a test of its version in ``base``; one ``base``
    doesn't have is added; one ``elements`` leaves out is removed after the same test. An image
    is only ever added: its key is its digest. An empty patch means nothing changed, which
    artifactr refuses, so a writer doesn't send it.
    """
    ops: list[dict[str, JsonValue]] = []
    for key, element in elements.items():
        before = base.elements.get(key)
        if before is None:
            ops.append({"op": "add", "path": _at(key), "value": _json(element)})
        elif _json(before) != _json(element):
            ops.extend(_replaced(key, before, element))
    for key, before in base.elements.items():
        if key not in elements:
            ops.append({"op": "test", "path": f"{_at(key)}/version", "value": before.version})
            ops.append({"op": "remove", "path": _at(key)})
    for digest, file in (files or {}).items():
        if digest not in base.files:
            ops.append({"op": "add", "path": f"/files/{digest}", "value": file.model_dump()})
    return JsonPatch(ops=tuple(ops))


def won(local: Element, remote: Element) -> bool:
    """Whether the local element wins over the remote one, as Excalidraw 0.18.1 decides.

    The higher version wins, and of two at one version, the lower nonce. (The canvas also keeps
    an element a person is editing, which only the canvas knows.)
    """
    if local.version != remote.version:
        return local.version > remote.version
    return local.version_nonce < remote.version_nonce


def reconcile(local: Mapping[str, Element], remote: Mapping[str, Element]) -> dict[str, Element]:
    """Every element of either, the winner where both have it, as ``reconcileElements``."""
    kept = {k: e for k, e in local.items() if k not in remote or won(e, remote[k])}
    return {**remote, **kept}


def rebase(base: Diagram, local: Mapping[str, Element], head: Diagram) -> dict[str, Element]:
    """A writer's elements, made from ``base``, moved onto ``head`` after a version conflict.

    Where an element the writer changed wins over the head's, it is sent again at one version
    above the head's (or its own, if higher), with a new nonce, so it wins once more when every
    canvas reconciles; where the head's wins, the writer's change is dropped. The
    :func:`element_patch` of the head and the result is what to send, with a new
    ``command_id``, unless it is empty.
    """
    changed = {
        key: element
        for key, element in local.items()
        if key not in base.elements or _json(base.elements[key]) != _json(element)
    }
    merged = dict(head.elements)
    for key, element in changed.items():
        theirs = head.elements.get(key)
        if theirs is None:
            merged[key] = element
        elif won(element, theirs):
            merged[key] = element.model_copy(
                update={
                    "version": max(element.version, theirs.version + 1),
                    "version_nonce": _nonce(),
                }
            )
    return merged


def _replaced(key: str, before: Element, after: Element) -> list[dict[str, JsonValue]]:
    return [
        {"op": "test", "path": f"{_at(key)}/version", "value": before.version},
        {"op": "replace", "path": _at(key), "value": _json(after)},
    ]


def _at(key: str) -> str:
    return f"/elements/{key}"  # an element's id has no "/" or "~" to escape


def _json(element: Element) -> dict[str, JsonValue]:
    return element.model_dump(mode="json")


def _nonce() -> int:
    return secrets.randbelow(MAX_NONCE) + 1
