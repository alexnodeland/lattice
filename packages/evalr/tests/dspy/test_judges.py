import dspy
import pytest
from dspy.utils import DummyLM
from opentelemetry import trace
from pydantic import ValidationError

from evalr.contracts import check_evaluator
from evalr.core import InputFormatter, estimate_tokens
from evalr.dspy import DspyJudge

from ..conftest import Spans, context_of
from .models import THREAD, Helpfulness, Thread, Tone

ANSWER = {
    "rating": "4",
    "resolved": "True",
    "category": "billing",
    "tone": "warm",
    "share": "0.8",
    "reason": "It refunded the charge",
}


def lm(*answers: dict[str, str]) -> DummyLM:
    return DummyLM(list(answers) or [ANSWER] * 10)


async def test_a_judge_gives_a_typed_verdict(spans: Spans) -> None:
    judge = DspyJudge(Helpfulness, inputs=Thread, lm=lm(), tracer_provider=spans.provider)
    verdict = await judge.evaluate(THREAD)
    assert verdict.value == Helpfulness(
        rating=4,
        resolved=True,
        category="billing",
        tone=Tone.WARM,
        share=0.8,
        reason="It refunded the charge",
    )
    assert (verdict.evaluator, verdict.version) == ("helpfulness-judge", judge.version)
    assert (verdict.confidence, verdict.cost) == ({}, None)
    (span,) = spans.finished()
    assert span.name == "evalr.evaluate helpfulness-judge"
    assert verdict.trace_id == trace.format_trace_id(context_of(span).trace_id)


async def test_empty_text_is_none() -> None:
    judge = DspyJudge(
        Helpfulness, inputs=Thread, lm=lm({**ANSWER, "reason": "None", "tone": "None"})
    )
    verdict = await judge.evaluate(THREAD)
    assert (verdict.value.reason, verdict.value.tone) == (None, None)


async def test_an_answer_out_of_bounds_is_invalid() -> None:
    judge = DspyJudge(Helpfulness, inputs=Thread, lm=lm({**ANSWER, "rating": "9"}))
    with pytest.raises(ValidationError, match="rating"):
        await judge.evaluate(THREAD)


def test_the_judge_reads_its_inputs_as_formatted_text_within_the_budget() -> None:
    whole = DspyJudge(Helpfulness, inputs=Thread)
    assert whole.inputs(THREAD) == {"request": THREAD.request, "reply": THREAD.reply}
    tight = DspyJudge(Helpfulness, inputs=Thread, formatter=InputFormatter(max_tokens=8))
    assert sum(estimate_tokens(v) for v in tight.inputs(THREAD).values()) <= 8


async def test_without_its_own_model_the_judge_uses_dspys() -> None:
    judge = DspyJudge(Helpfulness, inputs=Thread)
    assert judge.lm is None
    with dspy.context(lm=lm()):
        verdict = await judge.evaluate(THREAD)
    assert verdict.value.rating == 4


async def test_reasoning_uses_chain_of_thought() -> None:
    judge = DspyJudge(
        Helpfulness, inputs=Thread, reasoning=True, lm=lm({**ANSWER, "reasoning": "Refunded."})
    )
    assert isinstance(judge.program, dspy.ChainOfThought)
    assert (await judge.evaluate(THREAD)).value.rating == 4


def test_identity() -> None:
    judge = DspyJudge(Helpfulness, inputs=Thread, name="helpful")
    assert (judge.name, judge.verdict_type, judge.input_type) == ("helpful", Helpfulness, Thread)
    assert isinstance(judge.program, dspy.Predict)
    assert judge.instructions.startswith("Read the Thread")
    assert len(judge.version) == 12


def test_the_version_is_a_hash_of_the_program_and_types() -> None:
    same = DspyJudge(Helpfulness, inputs=Thread).version
    assert DspyJudge(Helpfulness, inputs=Thread, lm=lm()).version == same
    assert DspyJudge(Helpfulness, inputs=Thread, name="other").version == same
    assert DspyJudge(Helpfulness, inputs=Thread, instructions="Be strict.").version != same
    assert DspyJudge(Helpfulness, inputs=Thread, reasoning=True).version != same


async def test_the_judge_meets_the_evaluator_contract() -> None:
    await check_evaluator(DspyJudge(Helpfulness, inputs=Thread, lm=lm()), [THREAD, THREAD])
