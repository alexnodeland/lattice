# artifactr.langfuse

The `langfuse` extra. See [Observability](../guides/observability.md#langfuse) and [Evaluation](../guides/evaluation.md#scores-in-langfuse).

::: artifactr.langfuse
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Traces

::: artifactr.langfuse.langfuse_client

::: artifactr.langfuse.should_export_span

::: artifactr.langfuse.no_spans

::: artifactr.langfuse.langfuse_turn

::: artifactr.langfuse.turn_attributes

::: artifactr.langfuse.MAX_ATTRIBUTE

## Scores

Feedback's scores reach Langfuse through evalr's adapters, [`evalr.langfuse.LangfuseScoreSink`](../../evalr/reference/langfuse.md) and `LangfuseScoreConfigStore`, which a [`FeedbackMirror`](scores.md) and `sync_score_configs` take ([ADR-0049](../adr/0049-scores-on-evalr.md)).
