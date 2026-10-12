"""A draft rule's preview: how often it would have fired over a recent window of the log."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from reflexr import Envelope, Rule
from reflexr.core import RuleProgress, evaluate
from reflexr.workspace import Workspace

PAGE: Final = 500
"""How many envelopes each read of the log returns, newest first."""

MAX_PREVIEWED: Final = 10_000
"""The most envelopes a preview replays: the newest ones, if the window holds more."""


@dataclass(frozen=True)
class Preview:
    """How often a rule would have fired, had it watched the log since ``since``."""

    firings: int
    replayed: int
    """How many envelopes it replayed."""

    since: datetime
    complete: bool
    """Whether it replayed the whole window, rather than only its newest envelopes."""

    errors: int = 0
    """How many envelopes the rule's evaluation recorded as errors, as reflexr would."""


async def preview(
    workspace: Workspace, rule: Rule, *, since: datetime, limit: int = MAX_PREVIEWED
) -> Preview:
    """Replay the log since ``since`` through the rule, running nothing and writing nothing.

    It reads the log as the handle's actor, then folds it through reflexr's pure evaluation,
    from an empty state, as if the rule had been installed at the window's start.

    Args:
        workspace: The reflexr workspace the rule would run in.
        rule: The draft. It must pass :meth:`~reflexr.Rule.check` there, or it may fail here.
        since: The start of the window.
        limit: The most envelopes to replay.
    """
    envelopes, complete = await _window(workspace, since, limit)
    if not envelopes:
        return Preview(firings=0, replayed=0, since=since, complete=complete)
    progress = RuleProgress(cursor=envelopes[0].seq - 1, definition=rule.definition())
    evaluation = evaluate(rule, progress, {}, envelopes)
    return Preview(
        firings=len(evaluation.firings),
        replayed=len(envelopes),
        since=since,
        complete=complete,
        errors=len(evaluation.errors),
    )


async def _window(workspace: Workspace, since: datetime, limit: int) -> tuple[list[Envelope], bool]:
    """The envelopes logged since ``since``, oldest first, and whether that is all of them."""
    newest_first: list[Envelope] = []
    before: int | None = None
    while page := await workspace.read(before_seq=before, last=PAGE):
        for envelope in reversed(page):
            if envelope.ts < since:
                return newest_first[::-1], True
            if len(newest_first) == limit:
                return newest_first[::-1], False
            newest_first.append(envelope)
        before = page[0].seq
    return newest_first[::-1], True
