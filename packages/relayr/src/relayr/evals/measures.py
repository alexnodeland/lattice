"""Measures of the bridge's rules, read from the logs.

How people resolve the rules' proposals, and how many rules drafted in chat go live and stay live.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import artifactr
import artifactr.core as a
import reflexr.core
from reflexr.core import RuleName
from reflexr.workspace import Workspace
from relayr.evals.outcomes import EVALUATOR, ProposalOutcome
from relayr.rules import RULES_FROM_CHAT, RuleDraft


@dataclass(frozen=True)
class ProposalRates:
    """How people resolved one rule's proposals."""

    accepted: int = 0
    """Accepted as proposed."""

    edited: int = 0
    """Accepted with changes of their own."""

    rejected: int = 0

    @property
    def acceptance(self) -> float:
        """The share accepted, edited or not; 0 with none resolved."""
        total = self.accepted + self.edited + self.rejected
        return (self.accepted + self.edited) / total if total else 0.0

    @property
    def edit_rate(self) -> float:
        """The share of those accepted that people edited; 0 with none accepted."""
        kept = self.accepted + self.edited
        return self.edited / kept if kept else 0.0


async def proposal_rates(workspace: Workspace) -> dict[RuleName, ProposalRates]:
    """The proposal outcomes relayr's evaluator gave, counted by the rule whose run proposed."""
    counts: dict[RuleName, dict[str, int]] = {}
    for fact in await workspace.read(types=["reflexr:feedback_given"]):
        event = fact.event
        if (
            fact.actor != EVALUATOR
            or not isinstance(event, reflexr.core.FeedbackGiven)
            or event.feedback_type != ProposalOutcome.feedback_type
            or not isinstance(event.target, reflexr.core.RunTarget)
        ):
            continue
        rule = (await workspace.run(event.target.run_id)).rule
        outcome = ProposalOutcome.model_validate(event.value).outcome
        tally = counts.setdefault(rule, {})
        tally[outcome] = tally.get(outcome, 0) + 1
    return {rule: ProposalRates(**tally) for rule, tally in counts.items()}


@dataclass(frozen=True)
class RuleConversion:
    """How many rules drafted in chat were proposed, accepted, put live, and kept live."""

    proposed: int
    accepted: int
    installed: int
    """Rules relayr put live from accepted drafts."""

    eligible: int
    """Of those, the ones first put live at least ``survival`` ago."""

    survived: int
    """Of those, the ones never archived since: in reflexr, from their artifact, or by anyone."""

    @property
    def survival(self) -> float:
        """The share of eligible rules that survived; 0 with none eligible."""
        return self.survived / self.eligible if self.eligible else 0.0


async def rule_conversion(
    source: artifactr.Workspace,
    workspace: Workspace,
    *,
    now: datetime,
    survival: timedelta = timedelta(days=30),
) -> RuleConversion:
    """Count rules from chat through their life, from artifactr's proposals and reflexr's facts.

    A rule survives while no ``reflexr:rule_archived`` follows its first install, whoever
    archived it: a person, through its artifact, or an operator in reflexr directly.

    Args:
        source: The workspace in artifactr, where rules are drafted.
        workspace: The same workspace in reflexr, where they run.
        now: When to measure survival up to.
        survival: How long a rule must have been live to count.
    """
    drafts = [
        p
        for p in await source.proposals(status=None)
        if isinstance(p.change, a.CreateArtifact) and p.change.kind == RuleDraft.kind
    ]
    first: dict[RuleName, datetime] = {}
    archived: set[RuleName] = set()
    for fact in await workspace.read(types=["reflexr:rule_installed", "reflexr:rule_archived"]):
        event = fact.event
        if isinstance(event, reflexr.core.RuleArchived):
            archived.add(event.rule)
        elif (
            isinstance(event, reflexr.core.RuleInstalled)
            and isinstance(fact.actor, reflexr.core.AgentActor)
            and fact.actor.rule == RULES_FROM_CHAT.name
        ):
            first.setdefault(event.rule, fact.ts)
    eligible = [rule for rule, at in first.items() if now - at >= survival]
    return RuleConversion(
        proposed=len(drafts),
        accepted=sum(p.status == "accepted" for p in drafts),
        installed=len(first),
        eligible=len(eligible),
        survived=sum(rule not in archived for rule in eligible),
    )
