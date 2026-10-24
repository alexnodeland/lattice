"""Diagrams' revisions thinned, a day after they were saved (RFC-0006, artifactr ADR-0094).

Every save of a canvas is a revision, and every revision holds the whole scene: a person drawing
for an hour makes hundreds. After a day, a diagram's revisions are thinned to one an actor every
ten minutes, as the owner ratified (ADR-0091): of each actor's revisions in each ten minutes,
the latest is kept. Kept whatever their age, as the owner approved:

- the current version, which is what the diagram is;
- the first, the diagram as it was made;
- each one an accepted proposal made, so what was proposed and accepted is always there;
- the revisions pending proposals are based on, so a proposal is still compared and applied as
  it was made.

A revision saved before artifactr stamped a time counts as old, as the tombstone sweep counts it,
and its actor's undated revisions are one ten minutes. The log's events, which say what each
revision changed, are never thinned. Thinning makes the sweep date a tombstone later, never
earlier: it dates one by the first revision holding it, and an earlier one may be gone.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

from artifactr.core import EditArtifact, Revision
from artifactr.excalidraw.integrations import EXCALIDRAW
from artifactr.excalidraw.types import Diagram
from artifactr.workspace import Scope, Storage
from lattice_core.integrations import Integrations

__all__ = ["CHUNK", "THIN_AFTER", "THIN_EVERY", "thin_revisions", "thinned"]

THIN_AFTER: Final = timedelta(hours=24)
"""How old a revision is before it is thinned: one exactly so old is kept."""

THIN_EVERY: Final = timedelta(minutes=10)
"""Of each actor's old revisions, one is kept in every so long: the latest."""

CHUNK: Final = 500
"""The most versions forgotten in one call to the storage: a statement's parameters are few."""


def thinned(
    revisions: Sequence[Revision],
    *,
    now: datetime,
    based_on: frozenset[int] = frozenset(),
    after: timedelta = THIN_AFTER,
    every: timedelta = THIN_EVERY,
) -> list[int]:
    """The versions of an artifact's revisions, oldest first, that thinning forgets.

    Kept: the first and the current; each one an accepted proposal made; those in `based_on`;
    those `after` old or less; and of the older ones, each actor's latest in each `every`.

    Args:
        revisions: Its revisions, oldest first.
        now: The time, aware of its zone, as revisions' times are.
        based_on: Versions pending proposals are based on, which are kept.
        after: How old a revision is before it is thinned.
        every: Of an actor's old revisions in each such span, the latest is kept.

    Raises:
        ValueError: If `now` isn't aware of its time zone.
    """
    if now.tzinfo is None:
        raise ValueError("thinning's `now` names its time zone, as revisions' times do")
    seen: set[tuple[str, int | None]] = set()
    forgotten: list[int] = []
    # Newest first, so the first of an actor's span met is its latest, which is kept.
    for revision in reversed(revisions[1:-1]):  # the first and the current are kept
        at = revision.at
        if at is not None and at >= now - after:
            continue  # a day old at most
        if revision.proposal_id is not None or revision.version in based_on:
            continue  # an accepted proposal's, or a pending proposal's base
        span = (
            revision.actor.participant,
            None if at is None else int(at.timestamp() // every.total_seconds()),
        )
        if span in seen:
            forgotten.append(revision.version)
        seen.add(span)
    return sorted(forgotten)


async def thin_revisions(
    storage: Storage,
    scope: Scope,
    *,
    now: datetime,
    integrations: Integrations | None = None,
) -> int:
    """Thin a workspace's diagrams' revisions; how many were forgotten.

    It works on the storage, as the application's own maintenance, with no actor: it changes no
    diagram, only how much of its history is kept. Where `integrations` says diagrams are off in
    the workspace, nothing is thinned, as nothing is swept: a switched-off integration's
    artifacts are left as they are.

    Each diagram's revisions are read whole, a body each, and kept only as their version, actor,
    time and proposal (ADR-0094 says the cost).
    """
    if integrations is not None and not await integrations.is_enabled(
        scope.tenant_id, scope.workspace_id, EXCALIDRAW
    ):
        return 0
    histories: dict[str, list[Revision]] = {}
    for diagram in await storage.artifacts(scope, kind=Diagram.kind, include_archived=True):
        revisions = await storage.revisions(scope, diagram.id)
        histories[diagram.id] = [revision.model_copy(update={"data": {}}) for revision in revisions]
    # The revisions first, then the proposals: one made on a head after its diagram's revisions
    # were read is based on a revision this read didn't hold, which thinning never forgets.
    based_on: dict[str, set[int]] = defaultdict(set)
    for proposal in await storage.proposals(scope, status="pending"):
        if isinstance(proposal.change, EditArtifact):
            based_on[proposal.artifact_id].add(proposal.change.base_version)
    forgotten = 0
    for artifact_id, revisions in histories.items():
        versions = thinned(revisions, now=now, based_on=frozenset(based_on[artifact_id]))
        for at in range(0, len(versions), CHUNK):
            forgotten += await storage.drop_revisions(scope, artifact_id, versions[at : at + CHUNK])
    return forgotten
