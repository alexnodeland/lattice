"""End-to-end measures, defined generically: task completion, drop-off and rewrites.

Task completion is judged: a verdict type for any evaluator (a DSPy judge or a decision model)
reading a ``Transcript``. Drop-off and rewrites are computed from recorded activity, exactly and
cheaply. The libraries' ``[evals]`` extras put their logs into these inputs.
"""

from evalr.measures.completion import TaskCompletion, completion_rate
from evalr.measures.computed import (
    DropOff,
    Rewrites,
    drop_off_evaluator,
    drop_off_rate,
    measure_drop_off,
    measure_rewrites,
    rewrite_evaluator,
    rewrite_rate,
)
from evalr.measures.inputs import Activity, History, Revision, Role, Session, Transcript, Turn

__all__ = [
    "Activity",
    "DropOff",
    "History",
    "Revision",
    "Rewrites",
    "Role",
    "Session",
    "TaskCompletion",
    "Transcript",
    "Turn",
    "completion_rate",
    "drop_off_evaluator",
    "drop_off_rate",
    "measure_drop_off",
    "measure_rewrites",
    "rewrite_evaluator",
    "rewrite_rate",
]
