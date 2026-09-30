"""Langfuse for artifactr: the ``[langfuse]`` extra (ADR-0027).

An adapter (ADR-0034) that files artifactr's traces in Langfuse:

- :func:`should_export_span` keeps whole traces, not only their LLM spans, and :func:`no_spans`
  none, when a Collector sends Langfuse the traces
- :func:`langfuse_turn` is a ``TurnContext`` for the ``Runner`` that sets each turn's session,
  user, tags and metadata

Feedback reaches Langfuse as scores through evalr's adapters, ``evalr.langfuse``'s
``LangfuseScoreSink`` and ``LangfuseScoreConfigStore`` (ADR-0049)::

    langfuse = langfuse_client(tracer_provider=tracer_provider)
    runner = Runner(agent, app=deps, turn_context=langfuse_turn)
    await sync_score_configs(LangfuseScoreConfigStore(langfuse))
    mirror = FeedbackMirror(workspace, LangfuseScoreSink(langfuse), cursor="langfuse")
"""

from artifactr.langfuse.client import langfuse_client
from artifactr.langfuse.tracing import (
    MAX_ATTRIBUTE,
    langfuse_turn,
    no_spans,
    should_export_span,
    turn_attributes,
)

__all__ = [
    "MAX_ATTRIBUTE",
    "langfuse_client",
    "langfuse_turn",
    "no_spans",
    "should_export_span",
    "turn_attributes",
]
