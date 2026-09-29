# Function evaluators

Not every judgement needs a model. Whether a reply stayed under a length limit, whether a person rewrote what the agent wrote, whether a conversation ended with the agent waiting: these are computed, exactly and cheaply, from the input. `FunctionEvaluator` turns such a function into an evaluator, so its verdicts are typed, versioned, traced and scored like any other.

The examples on this page use the `Thread` type from [Getting started](../getting-started.md#1-define-the-types).

## A function as an evaluator

The function takes the input and returns an instance of the verdict type:

```python
from pydantic import BaseModel, Field

from evalr import FunctionEvaluator


class Politeness(BaseModel):
    """Whether the reply was polite."""

    polite: bool = Field(description="The reply thanks or apologizes to the person")


def polite(thread: Thread) -> Politeness:
    reply = thread.reply.lower()
    return Politeness(polite=any(word in reply for word in ("thank", "sorry", "apolog")))


evaluator = FunctionEvaluator(polite, verdict_type=Politeness, version="1")

verdict = await evaluator.evaluate(
    Thread(request="I was charged twice", reply="Sorry about that: I refunded the charge.")
)
print(verdict.value.polite, verdict.evaluator, verdict.version)
```

```text
True polite 1
```

- **The name** is the function's name unless you pass `name=`.
- **The version is yours to keep.** evalr cannot see inside a function, so the version is whatever you give (`"1"` by default). Bump it whenever the function's behaviour changes, so verdicts from the old and new functions are never mixed.
- **The function may be async**, for a measure that reads a database or calls a service: `FunctionEvaluator` awaits whatever it returns.
- **The result is checked.** A function that returns anything but the verdict type raises `TypeError`, and a verdict type with a field evalr cannot judge raises `UnsupportedField` when the evaluator is built.

Function evaluators give no confidence and no cost: their answers are exact, and free.

evalr's own computed measures are function evaluators: [`drop_off_evaluator` and `rewrite_evaluator`](measures.md) wrap drop-off and rewrites, versioned by their settings, so they run in [experiments](experiments.md) and [online](online.md) like any other evaluator.

## Traces

Every evaluation runs in an OpenTelemetry span named `evalr.evaluate {evaluator}`, with the attributes `evalr.evaluator.name`, `evalr.evaluator.version` and `evalr.verdict.type`. The span is current while the function runs, so anything it calls that is traced nests under it, and a failure is recorded on it. The verdict's `trace_id` is the span's trace, so a verdict made inside an experiment's item, or on the trace of the run it judges, links back to it.

evalr uses the OpenTelemetry API only and never configures the SDK. Spans go to the global tracer provider, which does nothing until the application configures one, or to the provider you pass as `tracer_provider=`. Without a provider, and outside any trace, `trace_id` is `None`.

## Your own evaluators

`FunctionEvaluator` suits a pure function. For anything with configuration of its own (a classifier, a rules engine, an external service), implement the `Evaluator` protocol directly. It asks for four things: a `name`, a `version`, a `verdict_type`, and `async evaluate(input)`. Build the verdict inside `judging`, the context manager every evaluator in evalr uses, which opens the span and stamps the verdict with the evaluator, its latency and the trace:

```python
import hashlib

from evalr import HandOff, Verdict
from evalr.core import get_tracer, judging


class Moderation(BaseModel):
    """Whether the reply is safe to show."""

    safe: bool = Field(description="The reply has no blocked words")


class KeywordModerator:
    """Flags replies that use a blocked word, and declines empty replies."""

    verdict_type = Moderation

    def __init__(self, blocked: set[str]) -> None:
        self.blocked = frozenset(word.lower() for word in blocked)
        self.name = "keyword-moderator"
        # The version follows the configuration, so a new word list is a new evaluator.
        self.version = hashlib.sha256(" ".join(sorted(self.blocked)).encode()).hexdigest()[:12]
        self._tracer = get_tracer()

    async def evaluate(self, input: Thread, /) -> Verdict[Moderation]:
        if not input.reply.strip():
            raise HandOff("the reply is empty")
        with judging(
            self._tracer, evaluator=self.name, version=self.version, verdict_type=Moderation
        ) as run:
            flagged = set(input.reply.lower().split()) & self.blocked
            return run.verdict(Moderation(safe=not flagged))


moderator = KeywordModerator({"idiot"})
verdict = await moderator.evaluate(Thread(request="Help?", reply="Here is the fix."))
print(verdict.value.safe, verdict.evaluator)
```

```text
True keyword-moderator
```

- `run.verdict(value, confidence=..., cost=...)` takes the confidence and cost where your evaluator knows them.
- **Derive the version from what decides the answers**, as evalr's own evaluators do: a DSPy judge hashes its program, a decision evaluator its model, instructions and thresholds.
- **Raise `HandOff` to decline an input**, for another evaluator to judge it. [`Fallback`](decision-evaluators.md#hand-off-and-fallback) catches it and asks its fallback; in [online evaluation](online.md) it is recorded, not raised. Any other exception is a failure.

`check_evaluator` in `evalr.contracts` checks that an evaluator of your own keeps the port's promises: every verdict is of the verdict type, names the evaluator and its version, and records the trace it was judged in ([Testing with the contracts](testing.md#your-own-adapters)).
