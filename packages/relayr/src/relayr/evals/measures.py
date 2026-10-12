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


async def proposal_rates(
    workspace: Workspace, *, since: datetime | None = None, until: datetime | None = None
) -> dict[RuleName, ProposalRates]:
    """The proposal outcomes relayr's evaluator gave, counted by the rule whose run proposed.

    It reads the workspace's feedback facts and its runs, each once: reflexr reads facts by type
    alone. A measure runs offline, as an experiment or a report, so it reads the whole log
    rather than a bounded window of it.

    Args:
        workspace: The workspace in reflexr.
        since: Count only outcomes given at or after this time.
        until: Count only outcomes given before this time.
    """
    scored: list[tuple[str, ProposalOutcome]] = []
    for fact in await workspace.read(types=["reflexr:feedback_given"]):
        event = fact.event
        if (
            fact.actor == EVALUATOR
            and isinstance(event, reflexr.core.FeedbackGiven)
            and event.feedback_type == ProposalOutcome.feedback_type
            and isinstance(event.target, reflexr.core.RunTarget)
            and (since is None or fact.ts >= since)
            and (until is None or fact.ts < until)
        ):
            scored.append((event.target.run_id, ProposalOutcome.model_validate(event.value)))
    rules = {run.id: run.rule for run in await workspace.runs()} if scored else {}
    counts: dict[RuleName, dict[str, int]] = {}
    for run_id, verdict in scored:
        tally = counts.setdefault(rules[run_id], {})
        tally[verdict.outcome] = tally.get(verdict.outcome, 0) + 1
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
    archived it: a person, through its artifact, or an operator in reflexr directly. Only what
    was logged before ``now`` counts, and the whole log is read, as for every measure.

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
    facts = await workspace.read(types=["reflexr:rule_installed", "reflexr:rule_archived"])
    for fact in facts:
        event = fact.event
        if fact.ts >= now:
            break
        if isinstance(event, reflexr.core.RuleArchived):
            if event.rule in first:  # an archive before relayr installed the rule doesn't count
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
