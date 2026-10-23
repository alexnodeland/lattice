"""The tombstone sweep: deleted elements removed a day after they were deleted (RFC-0006, U3).

A deleted element stays in its diagram as a tombstone, `isDeleted`, so that a client mid-edit
doesn't bring it back: Excalidraw's reconciliation keeps the higher version, and a tombstone
outranks the edit it ends. After a day no client holds it; the sweep removes it, as the
application's own actor, in one revision a diagram. Its age is the server's, from the revision
in which the element became the tombstone it is, never from the element's own `updated`, which a
client writes. Until it runs, a diagram at its limit of elements can't shrink (artifactr
ADR-0091).
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

from pydantic import JsonValue

from artifactr.core import EditArtifact, JsonPatch, Revision, SystemActor
from artifactr.excalidraw.types import Diagram, Element
from artifactr.workspace import Workspace

__all__ = ["KEEP", "SWEEPER", "sweep_tombstones"]

KEEP: Final = timedelta(hours=24)
"""How long a tombstone is kept after the revision that made it."""

SWEEPER: Final = SystemActor(name="excalidraw-sweep")
"""The actor the sweep commits as, which alone may remove an element from a diagram."""


async def sweep_tombstones(ws: Workspace, *, now: datetime, keep: timedelta = KEEP) -> int:
    """Remove the workspace's diagrams' tombstones older than `keep`; how many were removed.

    The handle is the sweep's own, as `SWEEPER`, and must see every artifact, as an application's
    own actor does. An archived diagram keeps its tombstones: it isn't edited. A diagram changed
    between the read and the sweep's commit is skipped, for the next sweep.
    """
    removed = 0
    for diagram in await ws.artifacts(Diagram):
        head = diagram.data
        tombstones = [e for e in head.elements.values() if e.is_deleted]
        if not tombstones:
            continue
        revisions = await ws.revisions(diagram.id)
        old = [e for e in tombstones if _deleted_before(e, revisions, now - keep)]
        if not old:
            continue
        ops: list[dict[str, JsonValue]] = []
        for element in old:
            ops.append(
                {"op": "test", "path": f"/elements/{element.id}/version", "value": element.version}
            )
            ops.append({"op": "remove", "path": f"/elements/{element.id}"})
        await ws.commit(
            EditArtifact(
                artifact_id=diagram.id,
                base_version=diagram.version,
                patch=JsonPatch(ops=tuple(ops)),
                summary=f"removed {len(old)} deleted elements",
            )
        )
        removed += len(old)
    return removed


def _deleted_before(element: Element, revisions: Sequence[Revision], before: datetime) -> bool:
    """Whether the revision that made this tombstone, as it is now, was committed before `before`.

    That is the first revision whose element has the tombstone's version: a revision with no
    time, saved before artifactr stamped one, counts as old.
    """
    for revision in revisions:
        elements = revision.data.get("elements")
        found = elements.get(element.id) if isinstance(elements, dict) else None
        if isinstance(found, dict) and found.get("version") == element.version:
            return revision.at is None or revision.at < before
    return False
