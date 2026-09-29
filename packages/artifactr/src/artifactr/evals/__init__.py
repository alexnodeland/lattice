"""evalr for artifactr: the ``[evals]`` extra (RFC-0002, ADR-0029, ADR-0044).

evalr owns evaluation: evaluators, datasets, optimizers and experiments behind ports. This
package adapts artifactr to them:

- :class:`LogFeedbackSource` is evalr's ``FeedbackSource`` over a workspace's log: typed
  feedback becomes examples, with inputs built from what the feedback is about; evaluators'
  own verdicts only when asked for.
- :func:`replay_task` is an evalr experiment ``Task`` that replays a thread's turn against a
  candidate agent, prompt or model in an isolated workspace.
- :class:`OnlineEvaluator` judges a Runner's turns as they end, sampled and within a budget,
  and records the verdicts as feedback from an :class:`~artifactr.core.EvaluatorActor`.
- :func:`thread_sessions` and :func:`artifact_histories` put the log into evalr's end-to-end
  measures, for drop-off and the rewrite rate; :class:`TaskCompletion` and
  :func:`completion_transcript` are for judging task completion.
"""

from artifactr.evals.context import BuildTurnInput, TargetContext, target_context
from artifactr.evals.experiments import REPLAYER, Replay, Seed, replay_task
from artifactr.evals.measures import (
    TaskCompletion,
    actor_role,
    artifact_histories,
    completion_transcript,
    thread_sessions,
)
from artifactr.evals.online import OnlineEvaluator
from artifactr.evals.source import BuildInput, FeedbackContext, LogFeedbackSource

__all__ = [
    "REPLAYER",
    "BuildInput",
    "BuildTurnInput",
    "FeedbackContext",
    "LogFeedbackSource",
    "OnlineEvaluator",
    "Replay",
    "Seed",
    "TargetContext",
    "TaskCompletion",
    "actor_role",
    "artifact_histories",
    "completion_transcript",
    "replay_task",
    "target_context",
    "thread_sessions",
]
