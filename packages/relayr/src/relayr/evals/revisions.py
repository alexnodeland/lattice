"""An artifact's history as evalr measures it: who wrote each version, when, and its text."""

import json

import artifactr
import artifactr.core as a
from evalr.measures import History, Revision, Role


async def history(source: artifactr.Workspace, artifact_id: a.ArtifactId) -> History:
    """Return an artifact's versions, for evalr's ``measure_rewrites`` and the like.

    A person's version is ``person``'s, and an agent's, a rule's or a client's is ``agent``'s.
    Each version's text is its data as canonical JSON, and its time is when artifactr logged it.
    Archiving changes no text, so an archive is no version here.

    Raises:
        NotFound: If there is no such artifact.
    """
    revisions = await source.revisions(artifact_id)
    logged = {
        envelope.event.version: envelope.ts
        for envelope in await source.read()
        if isinstance(envelope.event, a.ArtifactCreated | a.ArtifactChanged)
        and envelope.event.artifact_id == artifact_id
    }
    return History(
        id=artifact_id,
        revisions=[
            Revision(
                at=logged[revision.version],
                role=_role(revision.actor),
                text=json.dumps(revision.data, sort_keys=True),
            )
            for revision in revisions
            if not revision.archived
        ],
    )


def _role(actor: a.Actor) -> Role:
    return "person" if isinstance(actor, a.UserActor) else "agent"
