# artifactr.scores

Feedback as scores: the mirror, on evalr's mapping and ports. See [Evaluation](../guides/evaluation.md#scores) and [ADR-0049](../adr/0049-scores-on-evalr.md). It needs evalr, which the `langfuse` and `evals` extras install.

::: artifactr.scores
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## The mirror

::: artifactr.scores.FeedbackMirror

::: artifactr.scores.sync_score_configs

## Feedback types as scores

Each is evalr's function, with the feedback type's registered name as the `{type}` in its scores' names.

::: artifactr.scores.score_configs

::: artifactr.scores.score_values

## evalr's ports and values

`Score`, `ScoreConfig`, `ScoreSink`, `ScoreConfigStore`, `ScoreDataType` and `MAX_TEXT` are evalr's: import them from `evalr.core` ([evalr's reference](https://evalr.alexnodeland.com/reference/core/)).
