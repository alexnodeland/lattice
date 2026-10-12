"""An artifact's history as evalr measures it: who wrote each version, when, and its text."""

import json

import artifactr
import artifactr.core as a
from evalr.measures import History, Revision, Role


async def history(source: artifactr.Workspace, artifact_id: a.ArtifactId) -> History:
    """Return an artifact's versions, for evalr's ``measure_rewrites`` and the like.

    A version is its author's: an accepted proposal's version is its proposer's, not whoever
    accepted it, as artifactr records it. A person, or a client acting for one, is ``person``;
    the system is ``system``; an agent, a rule or a client acting for no one is ``agent``. Each
    version's text is its data as canonical JSON, and its time is when artifactr logged it.
    Archiving changes no text, so an archive is no version here. It reads the workspace's whole
    log once, as a measure does, to find when each version was logged.

    Raises:
        NotFound: If there is no such artifact.
    """
    revisions = await source.revisions(artifact_id)
    proposers = {
        proposal.id: proposal.proposed_by
        for proposal in await source.proposals(status="accepted")
        if proposal.artifact_id == artifact_id
    }
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
                role=_role(proposers.get(revision.proposal_id or "", revision.actor)),
                text=json.dumps(revision.data, sort_keys=True),
            )
            for revision in revisions
            if not revision.archived
        ],
    )


def _role(actor: a.Actor) -> Role:
    match actor:
        case a.UserActor() | a.ExternalAgentActor(on_behalf_of=a.UserActor()):
            return "person"
        case a.SystemActor():
            return "system"
        case _:
            return "agent"
