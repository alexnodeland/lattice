"""Measures computed from recorded activity, deterministically: drop-off and rewrites."""

from collections.abc import Iterable
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from evalr.core import FunctionEvaluator, Verdict
from evalr.measures.inputs import History, Revision, Session

__all__ = [
    "DropOff",
    "Rewrites",
    "drop_off_evaluator",
    "drop_off_rate",
    "measure_drop_off",
    "measure_rewrites",
    "rewrite_evaluator",
    "rewrite_rate",
]


class DropOff(BaseModel):
    """Whether a session ended with the agent waiting on a person who never came back."""

    outcome: Literal["continued", "dropped", "pending"] = Field(
        description="continued: a person acted after the agent's last turn, within the window; "
        "dropped: nobody did, or a proposal was left unresolved; pending: too soon to tell"
    )
    cause: Literal["no_reply", "unresolved_proposal"] | None = None


def measure_drop_off(session: Session, *, window: timedelta, now: datetime) -> DropOff:
    """Decide whether a session dropped off.

    A session dropped off when the agent acted last and no person acted within ``window``, or
    when a proposal was left unresolved for longer than ``window``. Until the window has passed,
    it is pending. A session whose last word was a person's continued.

    Args:
        session: The session's activity.
        window: How long a person has to come back.
        now: When the log was read: the end of the recording.
    """
    activities = sorted(session.activities, key=lambda a: a.at)
    resolved = {a.ref for a in activities if a.kind == "resolution"}
    for proposal in activities:
        if proposal.kind == "proposal" and proposal.ref not in resolved:
            if now - proposal.at >= window:
                return DropOff(outcome="dropped", cause="unresolved_proposal")
            return DropOff(outcome="pending")
    agent = [a for a in activities if a.role == "agent"]
    if not agent:
        return DropOff(outcome="continued")
    last = agent[-1].at
    replies = [a for a in activities if a.role == "person" and a.at > last]
    if any(a.at - last <= window for a in replies):
        return DropOff(outcome="continued")
    if replies or now - last >= window:
        return DropOff(outcome="dropped", cause="no_reply")
    return DropOff(outcome="pending")


def drop_off_rate(verdicts: Iterable[Verdict[DropOff]]) -> float | None:
    """The share of decided sessions that dropped off; ``None`` if none is decided."""
    outcomes = [v.value.outcome for v in verdicts if v.value.outcome != "pending"]
    return outcomes.count("dropped") / len(outcomes) if outcomes else None


def drop_off_evaluator(*, window: timedelta, now: datetime) -> FunctionEvaluator[Session, DropOff]:
    """Drop-off as an evaluator, versioned by its window."""

    def drop_off(session: Session) -> DropOff:
        return measure_drop_off(session, window=window, now=now)

    return FunctionEvaluator(
        drop_off, verdict_type=DropOff, name="drop-off", version=f"1:{window.total_seconds():g}s"
    )


class Rewrites(BaseModel):
    """How much of what an agent wrote people substantially rewrote."""

    agent_revisions: Annotated[int, Field(ge=0, description="Revisions the agent wrote")]
    rewritten: Annotated[int, Field(ge=0, description="Of those, the ones people rewrote")]
    rate: Annotated[float, Field(ge=0.0, le=1.0)] | None = Field(
        default=None, description="Rewritten over agent revisions; empty without any"
    )


def measure_rewrites(history: History, *, window: timedelta, threshold: float = 0.2) -> Rewrites:
    """Count the agent's revisions that a person substantially rewrote within a window.

    A person's revision rewrites the agent's when it comes within ``window`` after it, before
    the agent writes again, and changes at least ``threshold`` of its text (one minus
    ``difflib``'s similarity ratio). Of several such revisions, the last counts.

    Args:
        history: The artifact's revisions.
        window: How soon after the agent a person's change counts.
        threshold: The share of the text a change must alter to count as a rewrite.
    """
    revisions = sorted(history.revisions, key=lambda r: r.at)
    written = rewritten = 0
    for i, revision in enumerate(revisions):
        if revision.role != "agent":
            continue
        written += 1
        edits: list[Revision] = []
        for later in revisions[i + 1 :]:
            if later.role == "agent" or later.at - revision.at > window:
                break
            if later.role == "person":
                edits.append(later)
        if edits and _changed(revision.text, edits[-1].text) >= threshold:
            rewritten += 1
    return Rewrites(
        agent_revisions=written,
        rewritten=rewritten,
        rate=rewritten / written if written else None,
    )


def _changed(before: str, after: str) -> float:
    return 1.0 - SequenceMatcher(None, before, after).ratio()


def rewrite_rate(verdicts: Iterable[Verdict[Rewrites]]) -> float | None:
    """Rewritten over agent revisions across artifacts; ``None`` without any agent revision."""
    values = [v.value for v in verdicts]
    written = sum(v.agent_revisions for v in values)
    return sum(v.rewritten for v in values) / written if written else None


def rewrite_evaluator(
    *, window: timedelta, threshold: float = 0.2
) -> FunctionEvaluator[History, Rewrites]:
    """Rewrites as an evaluator, versioned by its window and threshold."""

    def rewrites(history: History) -> Rewrites:
        return measure_rewrites(history, window=window, threshold=threshold)

    return FunctionEvaluator(
        rewrites,
        verdict_type=Rewrites,
        name="rewrites",
        version=f"1:{window.total_seconds():g}s:{threshold:g}",
    )
