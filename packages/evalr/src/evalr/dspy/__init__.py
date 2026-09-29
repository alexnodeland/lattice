"""DSPy judges and GEPA (the ``[dspy]`` extra).

``DspyJudge`` adapts DSPy to the ``Evaluator`` port: its signature comes from the input and verdict
types, with the verdict fields' descriptions as instructions. ``Gepa`` adapts DSPy's GEPA to the
``Optimizer`` port, fitting a judge to people's verdicts and learning from their reasons
(ADR-0002, ADR-0006).
"""

from evalr.dspy.gepa import FeedbackMetric, Gepa, feedback_metric
from evalr.dspy.judges import FORMAT, DspyJudge, JudgeMismatch, SavedJudge, program_version
from evalr.dspy.signatures import default_instructions, judge_signature

__all__ = [
    "FORMAT",
    "DspyJudge",
    "FeedbackMetric",
    "Gepa",
    "JudgeMismatch",
    "SavedJudge",
    "default_instructions",
    "feedback_metric",
    "judge_signature",
    "program_version",
]
