from datetime import UTC, datetime, timedelta

import pytest

from evalr.core import Verdict, verdict_fields
from evalr.measures import (
    Activity,
    DropOff,
    History,
    Revision,
    Rewrites,
    Role,
    Session,
    TaskCompletion,
    completion_rate,
    drop_off_evaluator,
    drop_off_rate,
    measure_drop_off,
    measure_rewrites,
    rewrite_evaluator,
    rewrite_rate,
    share_changed,
)

T0 = datetime(2026, 9, 20, 9, tzinfo=UTC)
WINDOW = timedelta(minutes=30)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def act(minutes: float, role: Role, kind: str = "message", ref: str | None = None) -> Activity:
    return Activity(at=at(minutes), role=role, kind=kind, ref=ref)


def outcome(*activities: Activity, now: float = 120) -> tuple[str, str | None]:
    result = measure_drop_off(
        Session(id="s", activities=list(activities)), window=WINDOW, now=at(now)
    )
    return result.outcome, result.cause


@pytest.mark.parametrize(
    ("activities", "expected"),
    [
        ((act(0, "person"), act(1, "agent"), act(5, "person")), ("continued", None)),
        ((act(0, "person"), act(1, "agent")), ("dropped", "no_reply")),
        ((act(0, "person"), act(1, "agent"), act(60, "person")), ("dropped", "no_reply")),
        ((act(0, "person"), act(110, "agent")), ("pending", None)),
        ((act(0, "person"), act(1, "system")), ("continued", None)),
        (
            (act(0, "person"), act(1, "agent", "proposal", "p"), act(2, "person")),
            ("dropped", "unresolved_proposal"),
        ),
        (
            (
                act(0, "person"),
                act(1, "agent", "proposal", "p"),
                act(3, "person", "resolution", "p"),
            ),
            ("continued", None),
        ),
        ((act(100, "agent", "proposal", "p"), act(101, "person")), ("pending", None)),
    ],
    ids=[
        "reply",
        "no-reply",
        "late-reply",
        "too-soon",
        "no-agent",
        "unresolved",
        "resolved",
        "recent-proposal",
    ],
)
def test_drop_off(activities: tuple[Activity, ...], expected: tuple[str, str | None]) -> None:
    assert outcome(*activities) == expected


def test_activities_are_read_in_time_order() -> None:
    assert outcome(act(5, "person"), act(1, "agent"), act(0, "person")) == ("continued", None)


def verdict[V: DropOff | Rewrites | TaskCompletion](value: V) -> Verdict[V]:
    return Verdict(value=value, evaluator="e", version="1")


def test_drop_off_rate_counts_decided_sessions_only() -> None:
    verdicts = [
        verdict(DropOff(outcome="dropped", cause="no_reply")),
        verdict(DropOff(outcome="continued")),
        verdict(DropOff(outcome="pending")),
    ]
    assert drop_off_rate(verdicts) == 0.5
    assert drop_off_rate([verdict(DropOff(outcome="pending"))]) is None


def test_drop_off_rate_reads_values_without_verdicts() -> None:
    sessions = [
        Session(id="a", activities=[act(0, "person"), act(1, "agent")]),
        Session(id="b", activities=[act(0, "person"), act(1, "agent"), act(5, "person")]),
    ]
    measured = [measure_drop_off(s, window=WINDOW, now=at(120)) for s in sessions]
    assert drop_off_rate(measured) == 0.5
    assert drop_off_rate([measured[0], verdict(measured[1])]) == 0.5


def history(*revisions: tuple[float, Role, str]) -> History:
    return History(id="a", revisions=[Revision(at=at(m), role=r, text=t) for m, r, t in revisions])


PLAN = "Launch on Friday. Email customers on Thursday."
REWRITE = "Ship Monday after QA. Brief support first."
TYPO = "Launch on Friday. Email customers on Thursday!"


@pytest.mark.parametrize(
    ("revisions", "expected"),
    [
        (((0, "agent", PLAN), (5, "person", REWRITE)), (1, 1)),
        (((0, "agent", PLAN), (5, "person", TYPO)), (1, 0)),
        (((0, "agent", PLAN), (45, "person", REWRITE)), (1, 0)),
        (((0, "agent", PLAN), (5, "agent", PLAN), (6, "person", REWRITE)), (2, 1)),
        (((0, "agent", PLAN), (5, "person", TYPO), (9, "person", REWRITE)), (1, 1)),
        (((0, "person", PLAN), (5, "person", REWRITE)), (0, 0)),
        (((0, "agent", PLAN), (2, "system", REWRITE)), (1, 0)),
    ],
    ids=["rewrite", "typo", "too-late", "agent-again", "last-edit-counts", "no-agent", "system"],
)
def test_rewrites(
    revisions: tuple[tuple[float, Role, str], ...], expected: tuple[int, int]
) -> None:
    result = measure_rewrites(history(*revisions), window=WINDOW)
    assert (result.agent_revisions, result.rewritten) == expected
    assert result.rate == (expected[1] / expected[0] if expected[0] else None)


def test_the_rewrite_threshold_is_a_share_of_the_text() -> None:
    typo = history((0, "agent", PLAN), (5, "person", TYPO))
    assert measure_rewrites(typo, window=WINDOW, threshold=0.0).rewritten == 1


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("", "", 0.0),
        (PLAN, PLAN, 0.0),
        ("", PLAN, 1.0),
        ("abcd", "wxyz", 1.0),
        ("abcd", "abxd", 0.25),
    ],
    ids=["empty", "same", "written", "replaced", "one-of-four"],
)
def test_share_changed(before: str, after: str, expected: float) -> None:
    assert share_changed(before, after) == pytest.approx(expected)


# One row of a table of numbers, and one box of a checklist: difflib's autojunk heuristic calls
# either change a rewrite once the text reaches 200 characters, since every character is common.
TABLE = "\n".join(f"| Q{q} | {q * 37 % 900 + 100} | {q * 53 % 90 + 10} |" for q in range(1, 25))
CHECKLIST = "\n".join(["- [ ] todo"] * 24)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (TABLE, TABLE.replace("| Q6 | 322 | 58 |", "| Q6 | 555 | 11 |")),
        (CHECKLIST, CHECKLIST.replace("- [ ]", "- [x]", 1)),
    ],
    ids=["table", "checklist"],
)
def test_a_small_change_to_repetitive_text_is_small(before: str, after: str) -> None:
    assert share_changed(before, after) < 0.05
    rewrites = measure_rewrites(history((0, "agent", before), (5, "person", after)), window=WINDOW)
    assert rewrites.rewritten == 0


def test_rewrite_rate_pools_revisions() -> None:
    verdicts = [
        verdict(Rewrites(agent_revisions=3, rewritten=1, rate=1 / 3)),
        verdict(Rewrites(agent_revisions=1, rewritten=1, rate=1.0)),
        verdict(Rewrites(agent_revisions=0, rewritten=0)),
    ]
    assert rewrite_rate(verdicts) == 0.5
    assert rewrite_rate([]) is None
    assert rewrite_rate([v.value for v in verdicts]) == 0.5
    assert rewrite_rate([verdicts[0], verdicts[1].value]) == 0.5


def test_completion_rate() -> None:
    verdicts = [
        verdict(TaskCompletion(completed=True, quality=4)),
        verdict(TaskCompletion(completed=False, quality=2, reason="left hanging")),
    ]
    assert completion_rate(verdicts) == 0.5
    assert completion_rate([]) is None


def test_completion_rate_reads_peoples_feedback_without_verdicts() -> None:
    class Done(TaskCompletion):
        """A library's feedback type, as artifactr's ``TaskCompletion`` subclasses evalr's."""

    given = [Done(completed=True, quality=5), Done(completed=False, quality=1)]
    assert completion_rate(given) == 0.5
    judged = verdict(TaskCompletion(completed=True, quality=4))
    assert completion_rate([judged, *given]) == 2 / 3


def test_the_measures_are_judgeable_verdict_types() -> None:
    assert [f.kind for f in verdict_fields(TaskCompletion)] == ["binary", "ordinal", "text"]
    assert [f.kind for f in verdict_fields(DropOff)] == ["categorical", "categorical"]
    assert [f.kind for f in verdict_fields(Rewrites)] == ["numeric", "numeric", "numeric"]


async def test_evaluators_are_versioned_by_their_settings() -> None:
    drop = drop_off_evaluator(window=WINDOW, now=at(120))
    assert (drop.name, drop.version) == ("drop-off", "1:1800s")
    rewrites = rewrite_evaluator(window=WINDOW, threshold=0.3)
    assert (rewrites.name, rewrites.version) == ("rewrites", "2:1800s:0.3")
    verdict = await rewrites.evaluate(history((0, "agent", PLAN), (5, "person", REWRITE)))
    assert verdict.value.rewritten == 1
