"""A tenant's feedback and evaluations, summed by day from Langfuse's scores (portalr ADR-0027).

People's feedback is the scores no evaluator gave, from the libraries' feedback mirrors, which
Langfuse marks `API`: a thumb is a yes-or-no one, and what they wrote is a text one, or a score's
comment. An evaluation is an evaluator's numeric or yes-or-no score, averaged per day, a yes as 1
and a no as 0. Each day the window touches, in UTC, is in the summary, with nothing in it where
nothing was given; a score is counted on the day it was given.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, model_validator

from portalr.readers.langfuse import Langfuse, Score, Scores
from portalr.readers.query import Id, Span
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

COMMENTS: Final = 20
"""How many of people's comments the summary carries: the newest."""

MOST_DAYS: Final = 91
"""The longest window a summary sums, in days: a quarter, and a day's slack for its edges."""


class FeedbackQuery(Span):
    """Which feedback to sum: a window of at most ``MOST_DAYS``, and one workspace's, or all."""

    workspace: Id | None = None

    @model_validator(mode="after")
    def _at_most_a_quarter(self) -> Self:
        if self.end - self.start > timedelta(days=MOST_DAYS):
            raise ValueError(f"a window is at most {MOST_DAYS} days")
        return self


class Thumbs(BaseModel):
    """People's thumbs on one day, in UTC."""

    model_config = ConfigDict(frozen=True)

    day: date
    up: int
    down: int


class Mean(BaseModel):
    """An evaluation's scores on one day: how many, and their mean; None for a day with none."""

    model_config = ConfigDict(frozen=True)

    day: date
    count: int
    mean: float | None


class Evaluation(BaseModel):
    """One evaluator's score of one name, per day, and over the window."""

    model_config = ConfigDict(frozen=True)

    evaluator: str
    name: str
    count: int
    """How many there were, in all: the days' counts, summed."""
    days: list[Mean]


class WorkspaceTotals(BaseModel):
    """One workspace's thumbs and evaluations; None for traces tagged with no workspace."""

    model_config = ConfigDict(frozen=True)

    workspace: str | None
    up: int
    down: int
    evaluated: int


class Comment(BaseModel):
    """What a person wrote, on which trace, in which workspace, and when."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    trace_id: str
    workspace: str | None
    timestamp: datetime


class Feedback(BaseModel):
    """The window's feedback and evaluations, and whether every score was read."""

    model_config = ConfigDict(frozen=True)

    days: list[Thumbs]
    evaluations: list[Evaluation]
    """The most scored first."""
    workspaces: list[WorkspaceTotals]
    """The busiest first; a workspace with nothing counted isn't in it."""
    comments: list[Comment]
    """People's, the newest first."""
    complete: bool
    """False where a read stopped at one of its bounds: the sums are of the scores read."""


def day_of(at: datetime) -> date:
    """The day a moment is in, in UTC."""
    return at.astimezone(UTC).date()


def days_in(span: Span) -> list[date]:
    """Each day the span touches, in UTC, the first first."""
    first, last = day_of(span.start), day_of(span.end - timedelta(microseconds=1))
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def peoples(score: Score) -> bool:
    """Whether a person gave the score: no evaluator named it, and a library's mirror sent it."""
    return score.evaluator is None and score.source == "API"


def _numeric(score: Score) -> float | None:
    """A score to average: a yes-or-no as 1 or 0, a number as it is; else none.

    Langfuse sends a yes-or-no score's value as 1 or 0, which is read as a number.
    """
    if score.data_type == "BOOLEAN":
        return 1.0 if score.value else 0.0
    if score.data_type == "NUMERIC" and isinstance(score.value, int | float):
        return float(score.value)
    return None


def _said(score: Score) -> str | None:
    """What a person wrote: a text score's value, or a score's comment."""
    if score.data_type == "TEXT" and isinstance(score.value, str) and score.value:
        return score.value
    return score.comment or None


def summarize(read: Scores, span: Span) -> Feedback:
    """A read's scores, summed by day, by evaluation, and by workspace."""
    days = days_in(span)
    thumbs = {day: [0, 0] for day in days}
    evaluations: dict[tuple[str, str], dict[date, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    places: dict[str | None, list[int]] = {}
    comments: list[Comment] = []
    for score in read.scores:
        day = day_of(score.timestamp)
        if score.evaluator is not None:
            value = _numeric(score)
            if value is not None and day in thumbs:
                evaluations[score.evaluator, score.name][day].append(value)
            places.setdefault(score.workspace, [0, 0, 0])[2] += 1
        elif peoples(score):
            if score.data_type == "BOOLEAN" and day in thumbs:
                side = 0 if score.value else 1
                thumbs[day][side] += 1
                places.setdefault(score.workspace, [0, 0, 0])[side] += 1
            if (text := _said(score)) is not None:
                comments.append(
                    Comment(
                        id=score.id,
                        text=text,
                        trace_id=score.trace_id,
                        workspace=score.workspace,
                        timestamp=score.timestamp,
                    )
                )
    summed = [
        Evaluation(
            evaluator=evaluator,
            name=name,
            count=sum(len(values) for values in by_day.values()),
            days=[
                Mean(
                    day=day,
                    count=len(by_day.get(day, [])),
                    mean=sum(by_day[day]) / len(by_day[day]) if by_day.get(day) else None,
                )
                for day in days
            ],
        )
        for (evaluator, name), by_day in evaluations.items()
    ]
    return Feedback(
        days=[Thumbs(day=day, up=up, down=down) for day, (up, down) in thumbs.items()],
        evaluations=sorted(summed, key=lambda e: (-e.count, e.evaluator, e.name)),
        workspaces=sorted(
            (
                WorkspaceTotals(workspace=workspace, up=up, down=down, evaluated=evaluated)
                for workspace, (up, down, evaluated) in places.items()
            ),
            key=lambda place: (-(place.up + place.down + place.evaluated), place.workspace or ""),
        ),
        comments=sorted(comments, key=lambda comment: comment.timestamp, reverse=True)[:COMMENTS],
        complete=read.complete,
    )


async def read_feedback(
    langfuse: Langfuse, tenant: Tenant, query: FeedbackQuery
) -> Ok[Feedback] | Unavailable:
    """The tenant's feedback and evaluations in the window, or one workspace's, summed by day."""
    read = await langfuse.every_score(tenant, query, query.workspace)
    return read if isinstance(read, Unavailable) else Ok(data=summarize(read.data, query))
