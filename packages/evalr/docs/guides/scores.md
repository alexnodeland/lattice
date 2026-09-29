# Scores and score sinks

Observability backends record judgements as **scores**: named values attached to the traces or sessions they judge. evalr turns every verdict into scores, one per field, and records them through a **score sink**: in memory, in Langfuse, or as OpenTelemetry events. artifactr and reflexr turn people's feedback into scores with the same mapping, from evalr, so people's scores and evaluators' scores for the same field sit side by side ([ADR-0011](../adr/0011-scores-shared-with-the-libraries.md)).

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

A field left empty (`None` or `""`) gives no score, and a choice or text longer than `MAX_TEXT` (500 characters) is cut. Each score carries its evaluator and version, the field's confidence where the evaluator had one (the `metadata` above), and the trace it is attached to: the verdict's own unless you pass `trace_id=`. `span_id=` names the span within that trace that the verdict judges, where you know it.

## Names and ids

A score is named `{type}.{field}`. The type is the verdict type's class name in snake case (`Helpfulness` is `helpfulness`, `TaskCompletion` is `task_completion`), which is also how artifactr and reflexr name feedback types by default. Where a library registers the feedback type under another name, pass it, so the evaluator's scores land beside people's:

```python
scores(verdict, type_name="reply_helpfulness")  # reply_helpfulness.rating, and so on
```

A score's `id` is a UUID derived from what the verdict is about, the evaluator, its version and the score's name. What it is about is the `subject` you pass (a run id, a turn id, an example id), or else the verdict's trace, or else a hash of the verdict's value. So:

- **Recording a verdict again replaces its scores** rather than adding more: a store that keeps one score per id stays clean however often an evaluation is retried.
- **A new evaluator version adds new scores** rather than overwriting the old version's, so the two can be compared.

Pass `subject=` whenever the verdict has no trace, so two verdicts on different inputs cannot collide.

## Score configs

A backend that knows how to read a score (its data type, its range, its choices) can check the values it receives and offer the choices to people scoring by hand. `score_configs` describes each field of a type as a `ScoreConfig`, in the order of its fields:

```python
from evalr import score_configs

for config in score_configs(Helpfulness):
    print(config.name, config.data_type, config.minimum, config.maximum, config.categories)
```

```text
helpfulness.rating NUMERIC 1.0 5.0 ()
helpfulness.resolved BOOLEAN None None ()
helpfulness.reason TEXT None None ()
```

- **The data type** follows the field's kind, as in the table above, and `categories` holds a categorical field's choices as strings.
- **The bounds are kept as declared**: `Field(gt=0)` gives a minimum of 0, even on an `int`, where [`verdict_fields`](verdicts.md#field-kinds) reads 1. It is what the libraries have always created in Langfuse, and a config, once created, is never changed.
- **A field that cannot be scored is skipped**, where `verdict_fields` raises: a list, a nested model or a union of several types. A library's feedback type may have such fields.
- **`type_name=`** names the scores as a library registered the type, as for `scores`.

A `ScoreConfigStore` keeps configs by name: `names()` lists the ones it has, and `create(config)` adds one. `sync_score_configs` creates the configs a store lacks and leaves the others as they are, so a config's definition never changes under the scores that use it:

```python
from evalr import sync_score_configs
from evalr.memory import InMemoryScoreConfigStore

store = InMemoryScoreConfigStore()
print(await sync_score_configs(store, score_configs(Helpfulness)))
print(await sync_score_configs(store, score_configs(Helpfulness)))  # nothing new
```

```text
['helpfulness.rating', 'helpfulness.resolved', 'helpfulness.reason']
[]
```

`LangfuseScoreConfigStore` keeps them as Langfuse's score configs ([Scores in Langfuse](#scores-in-langfuse)), and artifactr and reflexr sync every feedback type they register into it.

## Feedback as scores

artifactr and reflexr keep people's feedback as JSON in their logs, and mirror it to a score sink. Their mirrors use evalr's mapping, so a person's `rating` and an evaluator's `rating` become the same score. `score_values` pairs each field of a validated value with its config and its score value, and takes a model's JSON as well as its fields:

```python
from evalr.core import score_values

feedback = {"rating": 2, "resolved": False, "reason": ""}
for config, value in score_values(Helpfulness, feedback, type_name="reply_helpfulness"):
    print(config.name, config.data_type, repr(value))
```

```text
reply_helpfulness.rating NUMERIC 2.0
reply_helpfulness.resolved BOOLEAN False
```

What the mapping does not decide stays in each library: which trace or session a piece of feedback is about, and the score's id. A mirror builds each `Score` itself, with no evaluator, and describes where the feedback came from in `source`, which a sink records with the rest of the score's metadata:

```python
from datetime import UTC, datetime

from evalr import Score

score = Score(
    id="0f6d2c1e-5b8a-5d3c-9e7f-1a2b3c4d5e6f",  # derived from the feedback's event and the name
    name="reply_helpfulness.rating",
    value=2.0,
    data_type="NUMERIC",
    session_id="thread_01",  # feedback on a whole thread; a turn's feedback names its trace
    timestamp=datetime(2026, 9, 29, 9, 30, tzinfo=UTC),  # when it was given
    source={"workspace_id": "support", "actor": "alice"},
)
print(score.metadata)
```

```text
{'workspace_id': 'support', 'actor': 'alice'}
```

A score's `metadata` is its `source`, then the evaluator, its version and the confidence, where it has them. A `Score` refuses what does not fit together: a value not of its data type (a `bool` for `BOOLEAN`, a `float` for `NUMERIC`, a string for `CATEGORICAL` and `TEXT`), a `source` key that would clash with the rest of its metadata (`evaluator`, `version` or `confidence`), and a span without a trace (`span_id` without `trace_id`).

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
| `LangfuseScoreSink(client)` | `evalr.langfuse` | In Langfuse, on the traces or sessions they judge |
| `OtelEventSink()` | `evalr.online` | As OpenTelemetry `gen_ai.evaluation.result` events ([Online evaluation](online.md#opentelemetry-events)) |

[Online evaluation](online.md) sends every verdict's scores to the sinks you give it, and the libraries' feedback mirrors send people's. A sink of your own is any class with an async `record(scores)`; check it with [`check_score_sink`](testing.md#your-own-adapters).

## Scores in Langfuse

`LangfuseScoreSink` records each score with the Langfuse client's `create_score`, on the score's trace or session. It needs the `langfuse` extra:

```python
from langfuse import Langfuse

from evalr.langfuse import LangfuseScoreSink

langfuse_scores = LangfuseScoreSink(Langfuse())
await langfuse_scores.record(scores(verdict))
await langfuse_scores.flush()  # before a short-lived process exits
```

- It records evaluators' scores and the libraries' mirrors of people's feedback alike.
- Each score keeps its id as Langfuse's `score_id`, so recording a verdict again replaces its scores in Langfuse too, and its span (as Langfuse's observation) and `timestamp`, where it has them. A yes or no is sent as 1 or 0.
- Evalr's online scores attach to the judged span as a Langfuse observation; if the Langfuse exporter filters that span out (v4's default keeps only LLM spans), the score names an observation Langfuse lacks.
- The score's `metadata` (its source, the evaluator, its version and the confidence) goes in Langfuse's metadata. Langfuse reads back a metadata value that parses as JSON as that JSON, so a version such as `"1"` (a `FunctionEvaluator`'s default) reads back as the number `1`.
- Langfuse attaches scores to traces or sessions, so if any score has neither, `record` raises `ValueError` and queues none of them.
- The client queues scores and sends them in the background; `flush()` waits until they are sent.

`LangfuseScoreConfigStore` keeps score configs as Langfuse's own, so Langfuse knows each score's type, range and choices:

```python
from evalr.langfuse import LangfuseScoreConfigStore

await sync_score_configs(LangfuseScoreConfigStore(Langfuse()), score_configs(Helpfulness))
```

- A config keeps its bounds, its description, and a categorical field's choices as Langfuse's categories, valued by their order.
- Langfuse takes a config name of at most 35 letters, digits, spaces and `_.()-`. Any other name is refused with `ValueError` before anything is sent: shorten the type's name (`type_name=`) or the field's.
- Its calls run in a worker thread, and `names()` reads every page of Langfuse's configs, archived ones included.

Scores from [experiments in Langfuse](experiments.md#experiments-in-langfuse) are recorded by Langfuse's experiment API instead, as each item's evaluations.
