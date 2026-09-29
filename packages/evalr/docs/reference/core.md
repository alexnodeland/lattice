# evalr.core

::: evalr.core
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## Verdicts

What an evaluator returns. See [Typed verdicts and field kinds](../guides/verdicts.md).

::: evalr.core.Verdict

::: evalr.core.Confidence

## Verdict fields

How each field of a verdict type is judged and scored. See [Field kinds](../guides/verdicts.md#field-kinds).

::: evalr.core.FieldKind

::: evalr.core.VerdictField

::: evalr.core.verdict_fields

::: evalr.core.canonical_fields

::: evalr.core.UnsupportedField

## Evaluators

The evaluator port, function evaluators and the hand-off composition. See [Function evaluators](../guides/function-evaluators.md) and [Hand-off and fallback](../guides/decision-evaluators.md#hand-off-and-fallback).

::: evalr.core.Evaluator

::: evalr.core.FunctionEvaluator

::: evalr.core.Fallback

::: evalr.core.HandOff

## Examples and datasets

Inputs with what people said about them, and where they come from and go. See [Datasets, splits and stores](../guides/datasets.md) and [Feedback sources](../guides/feedback-sources.md).

::: evalr.core.Example

::: evalr.core.Dataset

::: evalr.core.split_bucket

::: evalr.core.DatasetStore

::: evalr.core.DatasetNotFound

::: evalr.core.DuplicateExample

::: evalr.core.FeedbackSource

::: evalr.core.collect

## Formatters

The text a judge reads for an input, within a token budget. See [What a judge reads](../guides/dspy-judges.md#what-a-judge-reads).

::: evalr.core.Formatter

::: evalr.core.InputFormatter

::: evalr.core.TokenCounter

::: evalr.core.estimate_tokens

## Scores

Verdicts as named values, and the port they leave through. See [Scores and score sinks](../guides/scores.md).

::: evalr.core.Score

::: evalr.core.ScoreType

::: evalr.core.ScoreSink

::: evalr.core.scores

::: evalr.core.score_type_name

::: evalr.core.SCORE_NAMESPACE

## Experiments

A task run over a dataset, with every output judged. See [Experiments](../guides/experiments.md).

::: evalr.core.ExperimentTracker

::: evalr.core.Task

::: evalr.core.ExperimentResult

::: evalr.core.ItemResult

## Measuring and optimizing

An evaluator against people's verdicts, and fitted to them. See [Agreement and calibration metrics](../guides/metrics.md#measuring-an-evaluator) and [DSPy judges and GEPA](../guides/dspy-judges.md#training-with-gepa).

::: evalr.core.measure

::: evalr.core.Measurement

::: evalr.core.Optimizer

::: evalr.core.optimize

::: evalr.core.Training

::: evalr.core.DatasetRef

## Metrics

Agreement with people, calibration, and cost and latency. See [Agreement and calibration metrics](../guides/metrics.md).

::: evalr.core.agreement

::: evalr.core.Agreement

::: evalr.core.FieldAgreement

::: evalr.core.agreement_score

::: evalr.core.field_agreement

::: evalr.core.calibration

::: evalr.core.FieldCalibration

::: evalr.core.evaluator_stats

::: evalr.core.EvaluatorStats

::: evalr.core.accuracy

::: evalr.core.cohen_kappa

::: evalr.core.mean_absolute_error

::: evalr.core.spearman

::: evalr.core.brier_score

::: evalr.core.expected_calibration_error

## Tracing

OpenTelemetry spans for evaluations, through the API only. See [Your own evaluators](../guides/function-evaluators.md#your-own-evaluators).

::: evalr.core.judging

::: evalr.core.Judging

::: evalr.core.get_tracer

::: evalr.core.current_trace_id

::: evalr.core.SCOPE
