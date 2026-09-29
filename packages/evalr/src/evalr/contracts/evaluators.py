"""The ``Evaluator`` and ``Optimizer`` contracts."""

from collections.abc import Sequence
from typing import Any

from opentelemetry import trace
from pydantic import BaseModel

from evalr.contracts.support import require
from evalr.core import Dataset, Evaluator, HandOff, Optimizer, verdict_fields

__all__ = ["check_evaluator", "check_optimizer"]

_TRACE_ID = 0x0AF7651916CD43DD8448EB211C80319C
_PARENT = trace.NonRecordingSpan(
    trace.SpanContext(
        trace_id=_TRACE_ID,
        span_id=0x00F067AA0BA902B7,
        is_remote=False,
        trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
    )
)


async def check_evaluator[InputT: BaseModel, VerdictT: BaseModel](
    evaluator: Evaluator[InputT, VerdictT], inputs: Sequence[InputT]
) -> None:
    """Check that an evaluator gives well-formed verdicts, stamped and traced.

    Each input is judged inside a trace, which its verdict must record. An input the evaluator
    hands off is skipped, but it must judge at least one.

    Args:
        evaluator: The evaluator to check.
        inputs: Inputs it can judge.

    Raises:
        ContractViolation: The evaluator behaves differently from the ``Evaluator`` contract.
        UnsupportedField: Its verdict type cannot be judged.
    """
    verdict_fields(evaluator.verdict_type)
    name, version = evaluator.name, evaluator.version
    judged = 0
    for input in inputs:
        with trace.use_span(_PARENT, end_on_exit=False):
            try:
                verdict = await evaluator.evaluate(input)
            except HandOff:
                continue
        judged += 1
        require(
            isinstance(verdict.value, evaluator.verdict_type),
            f"a verdict must be a {evaluator.verdict_type.__name__}",
        )
        require(
            bool(verdict.evaluator) and bool(verdict.version),
            "a verdict must name the evaluator that gave it, and its version",
        )
        require(
            verdict.trace_id == trace.format_trace_id(_TRACE_ID),
            "a verdict must record the trace it was judged in",
        )
    require(judged > 0, "the evaluator must judge at least one of the inputs")
    require(
        (evaluator.name, evaluator.version) == (name, version),
        "judging must not change the evaluator's name or version",
    )


async def check_optimizer[InputT: BaseModel, VerdictT: BaseModel, EvaluatorT: Evaluator[Any, Any]](
    optimizer: Optimizer[InputT, VerdictT, EvaluatorT],
    evaluator: EvaluatorT,
    *,
    train: Dataset[InputT, VerdictT],
    validate: Dataset[InputT, VerdictT],
) -> None:
    """Check that an optimizer returns a working evaluator and leaves the one given alone.

    Args:
        optimizer: The optimizer to check.
        evaluator: An evaluator of the kind it fits.
        train: Labelled examples to fit on.
        validate: Labelled examples to check the fit on, none of them in ``train``.

    Raises:
        ContractViolation: The optimizer behaves differently from the ``Optimizer`` contract.
    """
    before = (evaluator.name, evaluator.version)
    fitted = await optimizer.optimize(evaluator, train=train, validate=validate)
    require(
        (evaluator.name, evaluator.version) == before,
        "optimizing must not change the evaluator it was given",
    )
    require(
        fitted.verdict_type is evaluator.verdict_type,
        "the fitted evaluator must give the same verdict type",
    )
    await check_evaluator(fitted, [example.input for example in validate])
