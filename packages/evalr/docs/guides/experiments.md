# Experiments

An experiment answers "is this change better?" before people see it. It runs a **task** (the system being evaluated: an agent, a prompt, a model) on every example of a dataset, and judges each output with every evaluator. Run it once for the current system and once for the candidate, and compare. evalr runs experiments in the process, or in Langfuse, where the results show beside each item's trace ([ADR-0003](../adr/0003-datasets-and-experiments-in-langfuse-and-hugging-face.md)).

The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types), and a [dataset](datasets.md) of threads.

## The task

A task is an async function from an example to an output, a Pydantic model that the evaluators judge. It receives the whole example (the input, people's verdict and the reference), so it can use any of them:

```python
from pydantic_ai import Agent

from evalr import Example

support_agent = Agent(
    "anthropic:claude-sonnet-5-5",
    instructions="You are a support agent. Fix the person's problem, then say what you did.",
)


async def reply(example: Example[Thread, Helpfulness]) -> Thread:
    """The system under test: the support agent, answering the example's request afresh."""
    result = await support_agent.run(example.input.request)
    return Thread(request=example.input.request, reply=result.output)
```

The output here is a new `Thread`, so any evaluator of threads can judge it. A task that returns the example's input unchanged measures the evaluators themselves against people's verdicts; [`measure`](metrics.md#measuring-an-evaluator) does that more directly.

## Running an experiment

```python
from evalr.decision import DecisionEvaluator
from evalr.memory import InMemoryExperimentTracker

tracker = InMemoryExperimentTracker()
decider = DecisionEvaluator(Helpfulness, inputs=Thread)

result = await tracker.run_experiment(
    "support-reply",
    dataset=dataset,
    task=reply,
    evaluators=[decider],
    metadata={"prompt": "v2"},
)

verdicts = result.verdicts("helpfulness-decision").values()
ratings = [verdict.value.rating for verdict in verdicts if isinstance(verdict.value, Helpfulness)]
print(result.run_name, len(result.items), sum(ratings) / len(ratings))
```

`result` is an `ExperimentResult`: the experiment's name, the run's name, the dataset's name and content hash, and one `ItemResult` per example, in the dataset's order. Each item has:

| Field | Holds |
|---|---|
| `example_id` | The example's id |
| `output` | The task's output, or `None` if the task failed |
| `verdicts` | One verdict per evaluator that succeeded, in the evaluators' order |
| `errors` | What failed: the task, or an evaluator by name, with its message |
| `trace_id` | The trace the example ran in, when there was one |

`result.verdicts(evaluator)` collects one evaluator's verdicts by example id. An experiment can mix evaluators of different verdict types, so their values are typed as `BaseModel`: check the type, as above, before reading a field.

- **A failure fails only its own item.** A task that raises leaves the item with no output and records the error; an evaluator that raises (or hands off) records its error while the other evaluators still judge.
- **Every example runs in its own trace**, and the task's own spans (the agent, its tools, its database calls) nest under it, so each verdict links to exactly what it judged.
- **`max_concurrency`** (4 by default) bounds how many examples run at once. **`metadata`** is kept with the run, for the model or prompt under test.

## Comparing systems

Evaluators judge outputs with the types people use, so any of evalr's summaries compares two runs: the share of threads [completed](measures.md#task-completion), the mean rating, or agreement between the candidate's verdicts and people's where the examples have them. Run the same dataset through both systems, with the same evaluators:

```python
from evalr import ExperimentResult


async def reply_v1(example: Example[Thread, Helpfulness]) -> Thread:
    """The system in production today: people's verdicts are about its replies."""
    return example.input


baseline = await tracker.run_experiment(
    "support-reply", dataset=dataset, task=reply_v1, evaluators=[decider]
)
candidate = await tracker.run_experiment(
    "support-reply", dataset=dataset, task=reply, evaluators=[decider]
)


def resolved_share(run: ExperimentResult[Thread]) -> float:
    verdicts = [v.value for v in run.verdicts("helpfulness-decision").values()]
    return sum(v.resolved for v in verdicts if isinstance(v, Helpfulness)) / len(verdicts)


print(resolved_share(baseline), resolved_share(candidate))
```

Before trusting an evaluator's verdict on a candidate, [measure it](metrics.md#measuring-an-evaluator) against people on the same kind of input: an experiment is only as good as its judges.

## In memory

`InMemoryExperimentTracker` runs experiments in the process and keeps every run in `runs`. It names runs `{name} #{n}` unless you pass `run_name=`, and runs each example in a span named `evalr.experiment.item {name}`, with the example's id and the run's metadata as attributes. Spans go to the global tracer provider, or the one you pass as `tracer_provider=`.

## Experiments in Langfuse

`LangfuseExperimentTracker` runs the same experiment through Langfuse's experiment API, so every item's trace, output and scores show in Langfuse's UI, and runs of one experiment can be compared there. It needs the `langfuse` extra, and uses your own client:

```python
from langfuse import Langfuse

from evalr.langfuse import LangfuseExperimentTracker

in_langfuse = LangfuseExperimentTracker(Langfuse())
result = await in_langfuse.run_experiment(
    "support-reply", dataset=dataset, task=reply, evaluators=[decider]
)
print(result.run_name, result.url)
```

- **Each example is an item with a trace of its own.** The item holds the example's input, `{"verdict": ..., "reference": ...}` as its expected output, and the example's id in its metadata. The task runs in the item's task span, and each evaluator in a span named after it, so everything they call nests under the item.
- **Every verdict becomes the item's scores**, named `{type}.{field}` like [any score](scores.md#names-and-ids), with the evaluator, its version and the confidence as metadata. Langfuse's evaluations hold no text, so a verdict's text fields (its reason) become the comment of its other scores.
- **Runs are named by Langfuse** (`{name} - {time}`) unless you pass `run_name=`. The examples go to Langfuse as local items rather than a Langfuse dataset's, so a run is one of the project's experiments, listed under its run name, not a dataset run, and `result.url` is `None`.
- The Langfuse client runs an experiment on an event loop of its own, in a worker thread. evalr runs your task and evaluators back on your event loop, where their clients live, carrying the trace context across, so they behave as they do anywhere else.

The dataset can come from anywhere; it does not have to be [saved in Langfuse](datasets.md#langfuse-datasets) first.
