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
from evalr.core.evaluators import FunctionEvaluator
from evalr.core.feedback import collect
from evalr.core.fields import FieldKind, UnsupportedField, VerdictField, verdict_fields
from evalr.core.formatting import Formatter, InputFormatter, TokenCounter, estimate_tokens
from evalr.core.ports import DatasetStore, Evaluator, FeedbackSource
from evalr.core.tracing import Judging, current_trace_id, get_tracer, judging
from evalr.core.verdicts import Confidence, Verdict

__all__ = [
    "Confidence",
    "Dataset",
    "DatasetNotFound",
    "DatasetStore",
    "DuplicateExample",
    "Evaluator",
    "Example",
    "FeedbackSource",
    "FieldKind",
    "Formatter",
    "FunctionEvaluator",
    "InputFormatter",
    "Judging",
    "TokenCounter",
    "UnsupportedField",
    "Verdict",
    "VerdictField",
    "collect",
    "current_trace_id",
    "estimate_tokens",
    "get_tracer",
    "judging",
    "split_bucket",
    "verdict_fields",
]
