"""evalr's core: verdicts, the evaluator protocol, datasets and metrics.

The core depends on pydantic and the OpenTelemetry API only, and performs no I/O. The
integrations (DSPy, Jev, Langfuse, Hugging Face) build on it from their own packages.
"""

from evalr.core.evaluators import Evaluator, FunctionEvaluator
from evalr.core.fields import FieldKind, UnsupportedField, VerdictField, verdict_fields
from evalr.core.tracing import Judging, current_trace_id, get_tracer, judging
from evalr.core.verdicts import Confidence, Verdict

__all__ = [
    "Confidence",
    "Evaluator",
    "FieldKind",
    "FunctionEvaluator",
    "Judging",
    "UnsupportedField",
    "Verdict",
    "VerdictField",
    "current_trace_id",
    "get_tracer",
    "judging",
    "verdict_fields",
]
