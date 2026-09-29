"""evalr's core, the hexagon: values, pure functions over them, and the ports.

The core depends on pydantic and the OpenTelemetry API only, and performs no I/O. The adapters
(DSPy, decision models, Langfuse, Hugging Face, files, in-memory) implement its ports from their
own packages (ADR-0006).
"""

from evalr.core.datasets import (
    Dataset,
    DatasetNotFound,
    DuplicateExample,
    Example,
    split_bucket,
)
from evalr.core.evaluators import Fallback, FunctionEvaluator, HandOff
from evalr.core.experiments import ExperimentResult, ItemResult, Task
from evalr.core.feedback import collect
from evalr.core.fields import FieldKind, UnsupportedField, VerdictField, verdict_fields
from evalr.core.formatting import Formatter, InputFormatter, TokenCounter, estimate_tokens
from evalr.core.measuring import Measurement, measure
from evalr.core.metrics import (
    Agreement,
    EvaluatorStats,
    FieldAgreement,
    FieldCalibration,
    accuracy,
    agreement,
    agreement_score,
    brier_score,
    calibration,
    cohen_kappa,
    evaluator_stats,
    expected_calibration_error,
    field_agreement,
    mean_absolute_error,
    spearman,
)
from evalr.core.optimizing import DatasetRef, Training, optimize
from evalr.core.ports import (
    DatasetStore,
    Evaluator,
    ExperimentTracker,
    FeedbackSource,
    Optimizer,
    ScoreSink,
)
from evalr.core.scores import SCORE_NAMESPACE, Score, ScoreType, score_type_name, scores
from evalr.core.tracing import Judging, current_trace_id, get_tracer, judging
from evalr.core.verdicts import Confidence, Verdict

__all__ = [
    "SCORE_NAMESPACE",
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
    "ScoreSink",
    "ScoreType",
    "Task",
    "TokenCounter",
    "Training",
    "UnsupportedField",
    "Verdict",
    "VerdictField",
    "accuracy",
    "agreement",
    "agreement_score",
    "brier_score",
    "calibration",
    "cohen_kappa",
    "collect",
    "current_trace_id",
    "estimate_tokens",
    "evaluator_stats",
    "expected_calibration_error",
    "field_agreement",
    "get_tracer",
    "judging",
    "mean_absolute_error",
    "measure",
    "optimize",
    "score_type_name",
    "scores",
    "spearman",
    "split_bucket",
    "verdict_fields",
]
