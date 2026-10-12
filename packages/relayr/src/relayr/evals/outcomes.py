"""How people resolve the rules' proposals, as feedback on the runs that proposed.

``relayr:proposal-outcome`` fires on a resolved proposal that a rule's participant made. It
re-reads artifactr, finds the run behind the proposal in the ledger, and gives that run a
``ProposalOutcome`` as relayr's evaluator: accepted as proposed, edited, or rejected. reflexr's
feedback mirror carries it on to a Langfuse score on the run.
"""

from collections.abc import Mapping
from typing import Any, Final, Literal

import artifactr
import artifactr.core as a
import reflexr.core
from reflexr import F, Feedback, Rule, on, run
from reflexr.workspace import Action, Reaction, Workspace
from relayr.events import ProposalResolved
from relayr.ledger import Ledger, WorkspaceKey
from relayr.outbound import is_rule_actor, rule_actor

type Outcome = Literal["accepted", "edited", "rejected"]


class ProposalOutcome(Feedback, name="proposal_outcome", targets={"run"}):
    """How a person resolved a rule's proposal.

    ``edited`` means they accepted it with changes of their own, so the artifact differs from
    what the proposal alone would have made.
    """

    outcome: Outcome


EVALUATOR: Final = reflexr.core.EvaluatorActor(name="relayr:proposal-outcome", version="1")
"""Who gives the outcomes: relayr's evaluator of the log."""

PROPOSAL_OUTCOME: Final = Rule(
    name="relayr:proposal-outcome",
    description="A rule's proposal was resolved. Score the run that made it.",
    when=on(ProposalResolved).where(F.proposed_by.kind.eq("external_agent")),
    then=run("proposal-outcome"),
)

RULES: Final = [PROPOSAL_OUTCOME]
"""relayr's evaluation rules, for the application's reflexr workspaces."""


class Outcomes:
    """The action of ``relayr:proposal-outcome``. Register `actions` with the reactor.

    Args:
        artifactr: The workspaces the runs re-read.
        ledger: The ledger relayr's adapters share, which holds the run behind each proposal.
    """

    def __init__(self, artifactr: artifactr.Workspaces, ledger: Ledger) -> None:
        self._artifactr = artifactr
        self._ledger = ledger

    @property
    def actions(self) -> Mapping[str, Action[Any]]:
        """The rule's action, by the name `PROPOSAL_OUTCOME` runs."""
        return {"proposal-outcome": self.score}

    async def score(self, reaction: Reaction[Any]) -> None:
        """Give the run behind a resolved proposal its outcome, once.

        It re-reads the proposal in artifactr rather than trust the bridged event, and gives
        nothing for a proposal no rule's run made, or one already scored.
        """
        [envelope] = reaction.events
        assert isinstance(envelope.event, ProposalResolved)
        target = reaction.workspace
        source = await self._artifactr.open(
            target.tenant_id, target.workspace_id, actor=rule_actor(reaction.run.rule)
        )
        try:
            proposal = await source.proposal(envelope.event.proposal_id)
        except a.NotFound:
            return
        if proposal.status == "pending" or not is_rule_actor(proposal.proposed_by):
            return
        key = WorkspaceKey(target.tenant_id, target.workspace_id)
        cause = await self._ledger.cause(key, "proposal", proposal.id)
        if cause is None:
            return
        on_run = reflexr.core.RunTarget(run_id=cause.run_id)
        if await _scored(target, on_run, envelope.seq):
            return
        outcome = "rejected" if proposal.status == "rejected" else await _how(source, proposal)
        await target.as_actor(EVALUATOR).give_feedback(ProposalOutcome(outcome=outcome), on=on_run)


async def _how(source: artifactr.Workspace, proposal: a.Proposal) -> Outcome:
    """``edited`` if the artifact the acceptance made differs from the proposal's change alone."""
    change = proposal.change
    if isinstance(change, a.ArchiveArtifact):
        return "accepted"  # an archive takes no changes
    revisions = await source.revisions(change.artifact_id)
    [made] = [r for r in revisions if r.proposal_id == proposal.id]
    if isinstance(change, a.CreateArtifact):
        alone = a.load_artifact(change.kind, change.data).to_json()
    else:
        [before] = [r for r in revisions if r.version == made.version - 1]
        alone = a.load_artifact(made.kind, a.apply_patch(before.data, change.patch)).to_json()
    return "accepted" if made.data == alone else "edited"


async def _scored(workspace: Workspace, on_run: reflexr.core.RunTarget, seq: int) -> bool:
    """Whether the evaluator scored a run already, for the resolution at ``seq``."""
    for fact in await workspace.read(types=["reflexr:feedback_given"]):
        event = fact.event
        if (
            fact.actor == EVALUATOR
            and isinstance(event, reflexr.core.FeedbackGiven)
            and event.target == on_run
            and fact.causation is not None
            and seq in (await workspace.run(fact.causation.run_id)).matched
        ):
            return True
    return False
