"""A tenant's feedback and evaluations, summed by day from Langfuse's scores (portalr ADR-0027).

People's feedback is the scores no evaluator gave; their thumbs are its yes-or-no scores. An
evaluation is an evaluator's numeric or yes-or-no score, averaged per day, a yes as 1 and a no as
0. Each day of the window is in the summary, with nothing in it where nothing was given.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from portalr.readers.langfuse import MOST_SCORES, Langfuse, Score
from portalr.readers.query import Id, Window
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant

COMMENTS = 20
"""How many of people's comments the summary carries: the newest."""


class FeedbackQuery(Window):
    """Which feedback to sum: a window's, and one workspace's, or every one's."""

    workspace: Id | None = None


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Thumbs(_Frozen):
    """People's thumbs on one day."""

    day: date
    up: int
    down: int


class Mean(_Frozen):
    """An evaluation's scores on one day: how many, and their mean; None for a day with none."""

    day: date
    count: int
    mean: float | None


class Evaluation(_Frozen):
    """One evaluator's score of one name, over the window, and per day."""

    evaluator: str
    name: str
    count: int
    days: list[Mean]


class Place(_Frozen):
    """One workspace's thumbs and evaluations; None for traces tagged with no workspace."""

    workspace: str | None
    up: int
    down: int
    evaluated: int


class Feedback(_Frozen):
    """The window's feedback and evaluations, and whether every score was read."""

    days: list[Thumbs]
    evaluations: list[Evaluation]
    """The most scored first."""
    workspaces: list[Place]
    """The busiest first."""
    comments: list[Score]
    """People's, with a comment, the newest first."""
    complete: bool
    """False where Langfuse had more scores than one read takes: the sums are of those read."""


def days_in(window: Window) -> list[date]:
    """Each day the window touches, in UTC, the first first."""
    first, last = window.start.date(), (window.end - timedelta(microseconds=1)).date()
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def _day(at: datetime) -> date:
    return at.date()


def _numeric(score: Score) -> float | None:
    """A score to average: a number as it is, a yes as 1 and a no as 0; else none."""
    if isinstance(score.value, bool):
        return 1.0 if score.value else 0.0
    if score.data_type == "NUMERIC" and isinstance(score.value, int | float):
        return float(score.value)
    return None


def summarize(scores: list[Score], window: Window) -> Feedback:
    """The scores of a window, summed by day, by evaluation, and by workspace."""
    days = days_in(window)
    thumbs = {day: [0, 0] for day in days}
    evaluations: dict[tuple[str, str], dict[date, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    places: dict[str | None, list[int]] = defaultdict(lambda: [0, 0, 0])
    for score in scores:
        place = places[score.workspace]
        if score.evaluator:
            place[2] += 1
            value = _numeric(score)
            if value is not None:
                evaluations[score.evaluator, score.name][_day(score.timestamp)].append(value)
        elif isinstance(score.value, bool):
            place[0 if score.value else 1] += 1
            if (counted := thumbs.get(_day(score.timestamp))) is not None:
                counted[0 if score.value else 1] += 1
    return Feedback(
        days=[Thumbs(day=day, up=up, down=down) for day, (up, down) in thumbs.items()],
        evaluations=sorted(
            (
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
            ),
            key=lambda evaluation: (-evaluation.count, evaluation.evaluator, evaluation.name),
        ),
        workspaces=sorted(
            (
                Place(workspace=workspace, up=up, down=down, evaluated=evaluated)
                for workspace, (up, down, evaluated) in places.items()
            ),
            key=lambda place: (-(place.up + place.down + place.evaluated), place.workspace or ""),
        ),
        comments=sorted(
            (score for score in scores if not score.evaluator and score.comment),
            key=lambda score: score.timestamp,
            reverse=True,
        )[:COMMENTS],
        complete=len(scores) < MOST_SCORES,
    )


async def feedback(
    langfuse: Langfuse, tenant: Tenant, query: FeedbackQuery
) -> Ok[Feedback] | Unavailable:
    """The tenant's feedback and evaluations in the window, or one workspace's, summed by day."""
    every = await langfuse.every_score(tenant, query, query.workspace)
    return every if isinstance(every, Unavailable) else Ok(data=summarize(every.data, query))
