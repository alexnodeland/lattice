# Online evaluation

Offline, an experiment tells you whether a change is better before people see it. Online, evaluators judge live traffic as the application serves it, so quality is measured continuously rather than sampled by people. `evalr.online` runs evaluators on live inputs: sampled by key, within a budget, in the trace of what they judge, and without ever breaking the application they watch ([ADR-0009](../adr/0009-online-evaluation.md)).

The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types).

## Judging live traffic

```python
import dspy
from langfuse import Langfuse
from opentelemetry import trace

from evalr import Fallback
from evalr.decision import DecisionEvaluator
from evalr.dspy import DspyJudge
from evalr.langfuse import LangfuseScoreSink
from evalr.online import Budget, OnlineEvaluation, OtelEventSink

decider = DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.7)
judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))

online = OnlineEvaluation(
    [Fallback(decider, judge)],  # Jev first; the judge only where Jev is unsure
    sample_rate=0.1,  # judge a tenth of the turns
    budget=Budget(max_cost=5.0),  # at most about $5 a day
    sinks=[LangfuseScoreSink(Langfuse()), OtelEventSink()],
)

tracer = trace.get_tracer("support-app")


async def handle_turn(turn_id: str, request: str) -> str:
    with tracer.start_as_current_span("turn"):
        reply = "I refunded the duplicate charge."  # your agent's reply
        online.submit(Thread(request=request, reply=reply), key=turn_id)
    return reply


await handle_turn("turn_01J9", "I was charged twice")
results = await online.drain()  # at shutdown: wait for everything submitted
```

`submit` returns at once and judges in the background, at most `max_concurrency` (8 by default) inputs at a time. `judge(input, key=)` does the same work and waits for it, returning the result.

## Sampling by key

An input is judged when `split_bucket(key, salt)`, the same hash that [splits datasets](datasets.md#splits), is below `sample_rate`. The key is the input's stable id, such as its turn or run id, so:

- the same turn is judged in every process, every retry and every replay, or never
- you know which inputs were sampled (`online.sampled(key)`), and can replay them
- `salt=` changes which inputs are chosen, without changing how many

## Budgets

`Budget(max_evaluations=, max_cost=, period=timedelta(days=1))` limits online evaluation per period, by the number of evaluations, their cost in US dollars, or both. It is checked before each evaluation and spent after it, so it is a soft limit: the evaluation that crosses it completes, and the ones in flight when it runs out can overshoot it. Leave that margin if you need a hard cap. An evaluator that hands off or fails still counts as an evaluation, and a period starts from nothing.

Evaluators left out because the budget was spent are recorded as `skipped`.

## The judged span

An online evaluation runs in the trace of the span it judges: the span current when `submit` or `judge` is called, or the `span=` you pass. Its spans nest under that span, even when it has already ended (as it usually has, since evaluation runs after the turn), and its scores record that span's trace and span id. So in Langfuse, or any tracing backend, a turn's evaluations appear inside the turn's trace.

## Results and sinks

Every verdict's [scores](scores.md) go to every sink, with the input's key as their subject, so re-judging a turn replaces its scores. `type_names={Helpfulness: "reply_helpfulness"}` names the scores of a verdict type the way a library registered it.

Nothing is raised. Each input gets an `OnlineResult`:

| Field | Holds |
|---|---|
| `key`, `sampled` | The input's key, and whether it was chosen |
| `verdicts` | The verdicts given, in the evaluators' order |
| `skipped` | Evaluators left out because the budget was spent |
| `handed_off` | Evaluators that handed the input off, with nothing to hand it to |
| `errors` | What failed: an evaluator or a sink, by name, with its message |

```python
for result in results:
    print(result.key, result.sampled, [v.evaluator for v in result.verdicts], result.errors)
```

Online evaluation must not break the application it watches, so an evaluator's failure, a sink's failure, a hand-off and a spent budget are all recorded rather than raised. Log or count them from the results.

## OpenTelemetry events

`OtelEventSink` records scores as OpenTelemetry `gen_ai.evaluation.result` events, following the GenAI semantic conventions, so evaluation data reaches any OpenTelemetry backend rather than one vendor's. It emits through the OpenTelemetry logs API, with the judged trace and span as each event's context: unlike an event added to the span itself, it can be emitted after the span has ended.

| Attribute | Holds |
|---|---|
| `gen_ai.evaluation.name` | The score's name, `{type}.{field}` |
| `gen_ai.evaluation.score.value` | A number, or 1 or 0 for a yes or no |
| `gen_ai.evaluation.score.label` | A choice, or `true` or `false` |
| `gen_ai.evaluation.explanation` | The verdict's text fields, such as its reason; a text field's own event has its text alone |
| `evalr.evaluator.name`, `evalr.evaluator.version` | Who judged, where an evaluator did |
| `evalr.score.id`, `evalr.confidence` | The score's id, and the evaluator's confidence where it has one |
| `session.id` | The session the score is attached to, where it has one |

An event's time is the score's `timestamp` where it has one, and otherwise when it was emitted. Events go to the global logger provider, which does nothing until the application configures the OpenTelemetry SDK's logs, or to the one you pass: `OtelEventSink(logger_provider)`. Events are append-only, so a reader that keys by `evalr.score.id` keeps the latest of each score.
