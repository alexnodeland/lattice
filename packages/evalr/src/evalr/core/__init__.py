"""evalr's core: verdicts, the evaluator protocol, datasets and metrics.

The core depends on pydantic and the OpenTelemetry API only, and performs no I/O. The
integrations (DSPy, Jev, Langfuse, Hugging Face) build on it from their own packages.
"""

from evalr.core.datasets import Dataset, DuplicateExample, Example, split_bucket
from evalr.core.evaluators import Evaluator, FunctionEvaluator
from evalr.core.fields import FieldKind, UnsupportedField, VerdictField, verdict_fields
from evalr.core.formatting import Formatter, InputFormatter, TokenCounter, estimate_tokens
from evalr.core.tracing import Judging, current_trace_id, get_tracer, judging
from evalr.core.verdicts import Confidence, Verdict

__all__ = [
    "Confidence",
    "Dataset",
    "DuplicateExample",
    "Evaluator",
    "Example",
    "FieldKind",
    "Formatter",
    "FunctionEvaluator",
    "InputFormatter",
    "Judging",
    "TokenCounter",
    "UnsupportedField",
    "Verdict",
    "VerdictField",
    "current_trace_id",
    "estimate_tokens",
    "get_tracer",
    "judging",
    "split_bucket",
    "verdict_fields",
]
