"""Decision evaluators: decision models such as TypeSafe's Jev, through pydantic-ai (``[jev]``).

``DecisionEvaluator`` adapts pydantic-ai's decision models to the ``Evaluator`` port: it answers a
verdict's fields as typed questions, with calibrated confidence, and hands off what it is unsure
of (ADR-0002, ADR-0006, ADR-0008).
"""

from evalr.decision.calibration import DEFAULT_GRID, ThresholdCalibration
from evalr.decision.evaluators import (
    DEFAULT_BOOLEAN_THRESHOLD,
    DEFAULT_MODEL,
    Decision,
    DecisionEvaluator,
)
from evalr.decision.views import MAX_CHOICES, DecisionView, decision_view

__all__ = [
    "DEFAULT_BOOLEAN_THRESHOLD",
    "DEFAULT_GRID",
    "DEFAULT_MODEL",
    "MAX_CHOICES",
    "Decision",
    "DecisionEvaluator",
    "DecisionView",
    "ThresholdCalibration",
    "decision_view",
]
