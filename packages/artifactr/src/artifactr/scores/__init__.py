"""Feedback as scores: the mirror that follows the log, on evalr's mapping and ports (ADR-0049).

Evaluation backends see feedback as scores, one per field. evalr owns how a field becomes a score,
the ``Score`` and ``ScoreConfig`` values, and the ports scores leave through: a ``ScoreSink`` for
scores and a ``ScoreConfigStore`` for score configs, which ``evalr.langfuse`` implements for
Langfuse. This package names each feedback type's scores as the type is registered, and mirrors
a workspace's feedback to a sink, following its log::

    mirror = FeedbackMirror(workspace, LangfuseScoreSink(langfuse), cursor="langfuse")
    task = asyncio.create_task(mirror.follow())  # after the cursor it saves in the workspace

It needs evalr, which the ``langfuse`` and ``evals`` extras install.
"""

from artifactr.scores.mapping import score_configs, score_values
from artifactr.scores.mirror import FeedbackMirror, sync_score_configs

__all__ = ["FeedbackMirror", "score_configs", "score_values", "sync_score_configs"]
