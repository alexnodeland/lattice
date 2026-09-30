"""The end-to-end measures on logs recorded from both libraries."""

from datetime import timedelta

from dspy.utils import DummyLM

from evalr.dspy import DspyJudge
from evalr.measures import (
    TaskCompletion,
    Transcript,
    completion_rate,
    drop_off_evaluator,
    drop_off_rate,
    rewrite_evaluator,
    rewrite_rate,
)

from .logs import (
    artifactr_histories,
    artifactr_sessions,
    artifactr_transcripts,
    recorded,
    reflexr_sessions,
    reflexr_transcripts,
)

WINDOW = timedelta(minutes=30)


async def test_drop_off_in_artifactr_threads() -> None:
    now, events = recorded("artifactr")
    evaluator = drop_off_evaluator(window=WINDOW, now=now)
    verdicts = {s.id: await evaluator.evaluate(s) for s in artifactr_sessions(events)}
    assert {thread: (v.value.outcome, v.value.cause) for thread, v in verdicts.items()} == {
        "t1": ("continued", None),
        "t2": ("dropped", "unresolved_proposal"),
        "t3": ("dropped", "no_reply"),
        "t4": ("pending", None),
    }
    assert drop_off_rate(verdicts.values()) == 2 / 3


async def test_rewrites_of_artifactr_artifacts() -> None:
    _, events = recorded("artifactr")
    evaluator = rewrite_evaluator(window=WINDOW)
    verdicts = {h.id: await evaluator.evaluate(h) for h in artifactr_histories(events)}
    assert {a: (v.value.agent_revisions, v.value.rewritten) for a, v in verdicts.items()} == {
        "a1": (1, 1),
        "a2": (1, 0),
    }
    assert rewrite_rate(verdicts.values()) == 0.5


async def test_drop_off_in_reflexr_chains() -> None:
    now, events = recorded("reflexr")
    evaluator = drop_off_evaluator(window=WINDOW, now=now)
    verdicts = {s.id: await evaluator.evaluate(s) for s in reflexr_sessions(events)}
    assert {chain: v.value.outcome for chain, v in verdicts.items()} == {
        "c1": "continued",
        "c2": "dropped",
        "c3": "continued",
    }
    assert drop_off_rate(verdicts.values()) == 1 / 3


def judge(answers: dict[str, dict[str, str]]) -> DspyJudge[Transcript, TaskCompletion]:
    return DspyJudge(TaskCompletion, inputs=Transcript, lm=DummyLM(answers))


async def test_task_completion_is_judged_on_both_libraries() -> None:
    _, artifactr = recorded("artifactr")
    _, reflexr = recorded("reflexr")
    done = {"completed": "True", "quality": "4", "reason": "Done."}
    undone = {"completed": "False", "quality": "2", "reason": "Left hanging."}
    completion = judge(
        {
            "Draft a launch plan": done,
            "Tighten the budget": undone,
            "Summarize the risks": done,
            "Any updates": done,
            "billing error": done,
            "search error": done,
        }
    )
    threads = artifactr_transcripts(artifactr)
    chains = reflexr_transcripts(reflexr)
    assert threads["t1"].result is not None
    assert threads["t1"].result.startswith("Ship Monday")
    by_thread = {t: await completion.evaluate(x) for t, x in threads.items()}
    by_chain = {c: await completion.evaluate(x) for c, x in chains.items()}
    assert completion_rate(by_thread.values()) == 3 / 4
    assert completion_rate(by_chain.values()) == 1.0
    assert by_thread["t2"].value.reason == "Left hanging."
