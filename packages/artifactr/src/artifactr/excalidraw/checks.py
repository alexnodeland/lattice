"""The checks that hold a diagram's edits to what Excalidraw's reconciliation needs (RFC-0006).

Give :func:`excalidraw_checks` to artifactr's ``Workspaces(checks=...)``. They run on every
surface, before an edit of a diagram commits, before a proposal of one is recorded, and again
when one is accepted, against the head it is applied to:

- **An element's version only grows.** An element an edit changes must have a ``version``
  greater than the head's, or the canvases that reconcile it would keep their own.
- **An element is never removed:** it is deleted by marking it ``isDeleted``, and kept, so a
  client mid-edit doesn't bring it back. Only the sweep, as ``SWEEPER``, removes a tombstone
  (RFC-0006, U3; :mod:`artifactr.excalidraw.sweep`).
- **A new element is an ``add``,** and an ``add`` of an id the head has already is refused:
  JSON Patch's ``add`` would replace it.
- **An image is added, never replaced or removed,** since its key is its digest.

What the type itself refuses, an element under another's key or a diagram past its limits, is
core's to refuse when it validates the result.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, NoReturn, cast

from pydantic import JsonValue

from artifactr.core import (
    ArtifactTarget,
    Command,
    EditArtifact,
    GiveFeedback,
    JsonPatch,
    ProposeChange,
    RespondToProposal,
    ValidationFailed,
    apply_patch,
    load_artifact,
)
from artifactr.excalidraw.sweep import SWEEPER
from artifactr.excalidraw.types import Diagram, DiagramComment
from artifactr.workspace import Check, Workspace

__all__ = ["excalidraw_checks"]

_ELEMENT: Final = "/elements/"


def excalidraw_checks() -> Mapping[str, Check]:
    """Return the diagrams' checks, by command type, for ``Workspaces(checks=...)``.

    An application that has checks of its own runs both for a command type: artifactr takes
    one check a type.
    """
    return MappingProxyType(
        {
            "edit_artifact": _check,
            "propose_change": _check,
            "respond_to_proposal": _check,
            "give_feedback": _check,
        }
    )


async def _check(workspace: Workspace, command: Command) -> None:
    match command:
        case EditArtifact():
            await _edited(workspace, command, on_head=False)
        case ProposeChange(change=EditArtifact() as change):
            await _edited(workspace, change, on_head=False)
        case RespondToProposal(decision="accept"):
            proposal = await workspace.proposal(command.proposal_id)
            if proposal.status == "pending" and isinstance(proposal.change, EditArtifact):
                await _edited(workspace, proposal.change, on_head=True)
        case GiveFeedback(feedback_type=DiagramComment.feedback_type):
            await _commented(workspace, command)
        case _:  # a rejection, or a proposal to make or archive one; another feedback
            pass


async def _commented(workspace: Workspace, command: GiveFeedback) -> None:
    """Refuse a comment on an element the diagram's version doesn't hold, live.

    Core has checked the value is a comment's, the target an artifact's version that exists.
    The version's own revision says what it held; one thinned away (ADR-0094), the head does.
    """
    target = command.target
    assert isinstance(target, ArtifactTarget), "core refuses a comment on all but an artifact"
    comment = DiagramComment.model_validate(command.value)
    artifact = await workspace.artifact(target.artifact_id)
    if not isinstance(artifact.data, Diagram):
        _refuse(["target", "artifact_id"], "a comment on an element is on a diagram")
    held, kept = artifact.data, False
    # Every revision is read to find one: a comment is rare beside a save, and thinning
    # (ADR-0094) keeps a diagram's revisions few after a day.
    for revision in await workspace.revisions(target.artifact_id):
        if revision.version == target.version:
            held, kept = Diagram.model_validate(revision.data), True
    element = held.elements.get(comment.element_id)
    if element is None or element.is_deleted:
        said = (
            f"version {target.version} of the diagram holds no element {comment.element_id}"
            if kept
            else f"version {target.version} is no longer kept, and the head holds no live "
            f"element {comment.element_id}"
        )
        _refuse(["value", "element_id"], said)


async def _edited(workspace: Workspace, command: EditArtifact, *, on_head: bool) -> None:
    """Check an edit against the head: as sent, or, for an accepted proposal, as rebased."""
    artifact = await workspace.artifact(command.artifact_id)
    stale = not on_head and artifact.version != command.base_version
    if stale or not isinstance(artifact.data, Diagram):
        return  # artifactr refuses a stale edit as a version conflict
    head = artifact.data
    ops = command.patch.ops if isinstance(command.patch, JsonPatch) else ()
    for op in ops:
        _added(head, op)
    # Loaded as core will load it, so data it refuses is refused here as core refuses it.
    after = cast("Diagram", load_artifact(Diagram.kind, apply_patch(head.to_json(), command.patch)))
    _kept(head, after)
    _grown(head, after, sweeping=workspace.actor == SWEEPER)


def _added(head: Diagram, op: Mapping[str, JsonValue]) -> None:
    path = str(op.get("path"))
    if op.get("op") == "add" and path.removeprefix(_ELEMENT) in head.elements:
        key = path.removeprefix(_ELEMENT)
        _refuse(["elements", key], f"element {key} exists: change it with a replace")


def _kept(head: Diagram, after: Diagram) -> None:
    """Every image the head has is still there, as it was, whatever the patch's paths say."""
    for digest, file in head.files.items():
        if after.files.get(digest) != file:
            _refuse(["files", digest], "an image is added, never replaced or removed")


def _grown(head: Diagram, after: Diagram, *, sweeping: bool) -> None:
    for key, before in head.elements.items():
        element = after.elements.get(key)
        if element is None and sweeping and before.is_deleted:
            continue  # the sweep's, of a tombstone
        if element is None:
            _refuse(
                ["elements", key],
                f"element {key} is deleted by marking it isDeleted, never removed: only the "
                "sweep removes a tombstone",
            )
        elif element.written() != before.written() and element.version <= before.version:
            _refuse(
                ["elements", key, "version"],
                f"element {key} changed, so its version must grow past {before.version}",
            )


def _refuse(loc: list[JsonValue], message: str) -> NoReturn:
    raise ValidationFailed(message, [{"type": "value_error", "loc": loc, "msg": message}])
