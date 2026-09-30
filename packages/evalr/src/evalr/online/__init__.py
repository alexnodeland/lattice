"""Online evaluation: judging live traffic, sampled and within a budget (ADR-0009).

``OnlineEvaluation`` runs evaluators on live inputs, in the trace of the span they judge, and
sends their scores to sinks; ``OtelEventSink`` is the sink that emits them as OpenTelemetry
``gen_ai.evaluation.result`` events, so evaluation data is not tied to one backend.
"""

from evalr.online.budgets import Budget
from evalr.online.events import EVALUATION_RESULT, OtelEventSink
from evalr.online.runner import OnlineEvaluation, OnlineResult

__all__ = ["EVALUATION_RESULT", "Budget", "OnlineEvaluation", "OnlineResult", "OtelEventSink"]
