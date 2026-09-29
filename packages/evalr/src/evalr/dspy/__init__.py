"""DSPy judges: language-model evaluators derived from their types (the ``[dspy]`` extra).

``DspyJudge`` adapts DSPy to the ``Evaluator`` port. Its signature comes from the input and
verdict types, with the verdict fields' descriptions as instructions (ADR-0002, ADR-0006).
"""

from evalr.dspy.judges import DspyJudge, program_version
from evalr.dspy.signatures import default_instructions, judge_signature

__all__ = ["DspyJudge", "default_instructions", "judge_signature", "program_version"]
