"""evalr: typed evaluation of agent systems.

An evaluator judges an input and returns a verdict: an instance of a Pydantic type, typically
one of the feedback types people also give, so evaluators can be trained on people's feedback
and measured against it:

```python
class Helpfulness(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")


evaluator = FunctionEvaluator(judge_by_rules, verdict_type=Helpfulness)
verdict = await evaluator.evaluate(transcript)  # Verdict[Helpfulness]
```

The top level re-exports every type in ``evalr.core``, and the functions most applications call.
See ``docs/architecture.md`` for the design.
"""

from importlib.metadata import version

from evalr.core import (
    Agreement,
    Confidence,
    Dataset,
    DatasetNotFound,
    DatasetRef,
    DatasetStore,
    DuplicateExample,
    Evaluator,
    EvaluatorStats,
    Example,
    ExperimentResult,
    ExperimentTracker,
    Fallback,
    FeedbackSource,
    FieldAgreement,
    FieldCalibration,
    FieldKind,
    Formatter,
    FunctionEvaluator,
    HandOff,
    InputFormatter,
    ItemResult,
    Judging,
    Measurement,
    Optimizer,
    Score,
    ScoreConfig,
    ScoreConfigStore,
    ScoreDataType,
    ScoreSink,
    Task,
    TokenCounter,
    Training,
    UnsupportedField,
    Verdict,
    VerdictField,
    agreement,
    calibration,
    collect,
    evaluator_stats,
    measure,
    optimize,
    score_configs,
    scores,
    sync_score_configs,
    verdict_fields,
)

__version__ = version("evalr")

__all__ = [
    "Agreement",
    "Confidence",
    "Dataset",
    "DatasetNotFound",
    "DatasetRef",
    "DatasetStore",
    "DuplicateExample",
    "Evaluator",
    "EvaluatorStats",
    "Example",
    "ExperimentResult",
    "ExperimentTracker",
    "Fallback",
    "FeedbackSource",
    "FieldAgreement",
    "FieldCalibration",
    "FieldKind",
    "Formatter",
    "FunctionEvaluator",
    "HandOff",
    "InputFormatter",
    "ItemResult",
    "Judging",
    "Measurement",
    "Optimizer",
    "Score",
    "ScoreConfig",
    "ScoreConfigStore",
    "ScoreDataType",
    "ScoreSink",
    "Task",
    "TokenCounter",
    "Training",
    "UnsupportedField",
    "Verdict",
    "VerdictField",
    "__version__",
    "agreement",
    "calibration",
    "collect",
    "evaluator_stats",
    "measure",
    "optimize",
    "score_configs",
    "scores",
    "sync_score_configs",
    "verdict_fields",
]
