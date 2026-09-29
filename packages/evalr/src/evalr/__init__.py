"""evalr: typed evaluation of agent systems.

An evaluator judges an input and returns a verdict: an instance of a Pydantic type, typically
one of the feedback types people also give, so evaluators can be trained on people's feedback
and measured against it::

    class Helpfulness(BaseModel):
        rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
        resolved: bool = Field(description="The request was fully addressed")


    evaluator = FunctionEvaluator(judge_by_rules, verdict_type=Helpfulness)
    verdict = await evaluator.evaluate(transcript)  # Verdict[Helpfulness]

See ``docs/architecture.md`` for the design.
"""

from importlib.metadata import version

from evalr.core import (
    Evaluator,
    FieldKind,
    FunctionEvaluator,
    UnsupportedField,
    Verdict,
    VerdictField,
    verdict_fields,
)

__version__ = version("evalr")

__all__ = [
    "Evaluator",
    "FieldKind",
    "FunctionEvaluator",
    "UnsupportedField",
    "Verdict",
    "VerdictField",
    "__version__",
    "verdict_fields",
]
