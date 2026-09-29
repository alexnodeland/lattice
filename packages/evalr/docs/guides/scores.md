# Scores and score sinks

Observability backends record judgements as **scores**: named values attached to the traces they judge. evalr turns every verdict into scores, one per field, and records them through a **score sink**: in memory, in Langfuse, or as OpenTelemetry events. The names and types follow the convention artifactr and reflexr use for people's feedback, so people's scores and evaluators' scores for the same field sit side by side.

The examples on this page use the `Helpfulness` type from [Getting started](../getting-started.md#1-define-the-types).

## A verdict as scores

`scores(verdict)` gives one `Score` per field of the verdict that has a value, in the order of the type's fields:

```python
from evalr import Verdict, scores

verdict = Verdict(
    value=Helpfulness(rating=4, resolved=True, reason="It refunded the charge"),
    confidence={"rating": 0.8, "resolved": 0.93},
    evaluator="helpfulness-decision",
    version="7cb26270254b",
    trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
)

for score in scores(verdict):
    print(score.name, score.data_type, repr(score.value), score.metadata)
```

```text
helpfulness.rating NUMERIC 4.0 {'evaluator': 'helpfulness-decision', 'version': '7cb26270254b', 'confidence': 0.8}
helpfulness.resolved BOOLEAN True {'evaluator': 'helpfulness-decision', 'version': '7cb26270254b', 'confidence': 0.93}
helpfulness.reason TEXT 'It refunded the charge' {'evaluator': 'helpfulness-decision', 'version': '7cb26270254b'}
```

The field's [kind](verdicts.md#field-kinds) decides the score's data type and value:

| Field kind | Data type | Value |
|---|---|---|
| binary | `BOOLEAN` | `True` or `False` |
| ordinal, numeric | `NUMERIC` | a `float` |
| categorical | `CATEGORICAL` | the choice as a string (an `Enum`'s value) |
| text | `TEXT` | the text |

A field left empty gives no score. Each score carries its evaluator and version, the field's confidence where the evaluator had one (the `metadata` above), and the trace it is attached to: the verdict's own unless you pass `trace_id=`. `span_id=` names the span within that trace that the verdict judges, where you know it.

## Names and ids

A score is named `{type}.{field}`. The type is the verdict type's class name in snake case (`Helpfulness` is `helpfulness`, `TaskCompletion` is `task_completion`), which is also how artifactr and reflexr name feedback types by default. Where a library registers the feedback type under another name, pass it, so the evaluator's scores land beside people's:

```python
scores(verdict, type_name="reply_helpfulness")  # reply_helpfulness.rating, and so on
```

A score's `id` is a UUID derived from what the verdict is about, the evaluator, its version and the score's name. What it is about is the `subject` you pass (a run id, a turn id, an example id), or else the verdict's trace, or else a hash of the verdict's value. So:

- **Recording a verdict again replaces its scores** rather than adding more: a store that keeps one score per id stays clean however often an evaluation is retried.
- **A new evaluator version adds new scores** rather than overwriting the old version's, so the two can be compared.

Pass `subject=` whenever the verdict has no trace, so two verdicts on different inputs cannot collide.

## Score sinks

A `ScoreSink` records scores, idempotently by id: recording a score again replaces it, and the latest value wins. It is one method:

```python
from evalr.memory import InMemoryScoreSink

sink = InMemoryScoreSink()
await sink.record(scores(verdict))
await sink.record(scores(verdict))  # replaces, does not add
print(len(sink.scores))
```

```text
3
```

| Sink | Package | Records scores |
|---|---|---|
| `InMemoryScoreSink` | `evalr.memory` | In memory, by id, for tests |
| `LangfuseScoreSink(client)` | `evalr.langfuse` | In Langfuse, on the traces they judge |
| `OtelEventSink()` | `evalr.online` | As OpenTelemetry `gen_ai.evaluation.result` events ([Online evaluation](online.md#opentelemetry-events)) |

[Online evaluation](online.md) sends every verdict's scores to the sinks you give it. A sink of your own is any class with an async `record(scores)`; check it with [`check_score_sink`](testing.md#your-own-adapters).

## Scores in Langfuse

`LangfuseScoreSink` records each score with the Langfuse client's `create_score`, on the score's trace. It needs the `langfuse` extra:

```python
from langfuse import Langfuse

from evalr.langfuse import LangfuseScoreSink

langfuse_scores = LangfuseScoreSink(Langfuse())
await langfuse_scores.record(scores(verdict))
await langfuse_scores.flush()  # before a short-lived process exits
```

- Each score keeps its id as Langfuse's `score_id`, so recording a verdict again replaces its scores in Langfuse too.
- The evaluator, its version and the confidence go in the score's metadata.
- Langfuse attaches scores to traces, so a score without a trace is refused with `ValueError`.
- The client queues scores and sends them in the background; `flush()` waits until they are sent.

Scores from [experiments in Langfuse](experiments.md#experiments-in-langfuse) are recorded by Langfuse's experiment API instead, as each item's evaluations.
