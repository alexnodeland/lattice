"""Feedback as scores: the mapping, the mirror that follows the log, and its ports (ADR-0034).

Evaluation backends see feedback as scores, one per field. This package maps feedback types to
scores and score configs, and mirrors a workspace's feedback to a :class:`ScoreSink`, following
its log. The sink and the :class:`ScoreConfigStore` are ports; ``artifactr.langfuse`` adapts
Langfuse to them::

    mirror = FeedbackMirror(workspace, sink)
    task = asyncio.create_task(mirror.follow())
"""

from artifactr.scores.mapping import (
    MAX_TEXT,
    ScoreConfig,
    ScoreDataType,
    score_configs,
    score_values,
)
from artifactr.scores.mirror import FeedbackMirror, sync_score_configs
from artifactr.scores.ports import Score, ScoreConfigStore, ScoreSink

__all__ = [
    "MAX_TEXT",
    "FeedbackMirror",
    "Score",
    "ScoreConfig",
    "ScoreConfigStore",
    "ScoreDataType",
    "ScoreSink",
    "score_configs",
    "score_values",
    "sync_score_configs",
]
