# Architecture

> **Status:** accepted design, being built in the phases tracked by [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). This document is evergreen: it is updated in the same pull request as the code that changes it, and the table below shows what exists today. Decisions are recorded in [`adr/`](adr/README.md), and proposals in [`rfcs/`](rfcs/README.md).

| Package | Status |
|---|---|
| `evalr.core` | Implemented |
| `evalr.memory`, `evalr.contracts`, `evalr.jsonl` | Implemented |
| `evalr.dspy` | `DspyJudge` implemented; GEPA and saved judges planned (phase 2) |
| `evalr.decision` | Planned (phase 3) |
| `evalr.langfuse`, `evalr.hf` | Planned (phase 4) |
| End-to-end measures and online helpers | Planned (phase 5) |

## What evalr is

evalr is a Python library for **typed evaluation of agent systems**. An evaluator judges an input (a chat thread, a workflow run, an artifact version) and returns a verdict: an instance of a Pydantic type, typically one of the feedback types people also give. Because people and evaluators produce the same types, evaluators can be trained on people's feedback and measured against it.

It serves [artifactr](https://github.com/alexnodeland/artifactr) and [reflexr](https://github.com/alexnodeland/reflexr), which record typed feedback from people and depend on evalr through their `[evals]` extras. evalr imports neither ([ADR-0001](adr/0001-typed-verdicts-over-any-pydantic-model.md)).

### Goals

- Verdicts are typed. A verdict type is any Pydantic model, and its field types decide how each field is judged and scored.
- Two kinds of evaluator are equals ([ADR-0002](adr/0002-dspy-judges-and-decision-models-as-equals.md)): DSPy judges optimized with GEPA, and decision models (TypeSafe's Jev) with a language-model fallback. Both implement one protocol and are measured with the same metrics.
- Evaluators are versioned, and the version is recorded on every verdict, so scores from different evaluators never mix.
- Datasets and experiments are reproducible: deterministic splits, deterministic dataset item ids, pinned revisions ([ADR-0003](adr/0003-datasets-and-experiments-in-langfuse-and-hugging-face.md)).
- The core is small and pure. Every integration is an adapter behind one of its ports, and behind an extra.

### Non-goals (for now)

- A hosted evaluation service or a UI. Langfuse shows experiments and scores; Hugging Face hosts published datasets.
- Evaluators for every modality. Inputs are Pydantic models turned into text.

## Ports and adapters

evalr is built as ports and adapters ([ADR-0006](adr/0006-ports-and-adapters.md)). `evalr.core` is the hexagon: the values (verdicts, examples, datasets, scores, experiment results), the pure functions over them, and the **ports**, small protocols for what the core needs from outside. **Adapters** implement the ports, each in its own package, and depend inward only.

```mermaid
graph LR
    subgraph adapters["Adapters"]
        dspy["evalr.dspy<br/>DspyJudge, GEPA"]
        decision["evalr.decision<br/>DecisionEvaluator, calibration"]
        langfuse["evalr.langfuse<br/>datasets, scores, experiments"]
        hf["evalr.hf<br/>Hugging Face datasets"]
        jsonl["evalr.jsonl<br/>JSON Lines datasets"]
        memory["evalr.memory<br/>in-memory, every port"]
        libs["artifactr, reflexr<br/>[evals] extras"]
    end
    subgraph core["evalr.core"]
        ports["Evaluator, Optimizer, DatasetStore,<br/>ScoreSink, ExperimentTracker,<br/>FeedbackSource, Formatter"]
        values["verdicts, datasets, splits,<br/>formatters, metrics"]
    end
    dspy --> ports
    decision --> ports
    langfuse --> ports
    hf --> ports
    jsonl --> ports
    memory --> ports
    libs --> ports
```

| Port | What it does | Adapters |
|---|---|---|
| `Evaluator[InputT, VerdictT]` | Judges an input and returns a typed verdict | `FunctionEvaluator` (core), `DspyJudge` (`evalr.dspy`), `DecisionEvaluator` (`evalr.decision`); compositions: `Fallback` (core), sampling and budgets (phase 5) |
| `Optimizer[InputT, VerdictT, EvaluatorT]` | Fits an evaluator to people's verdicts | GEPA (`evalr.dspy`), threshold calibration (`evalr.decision`), in-memory (`evalr.memory`) |
| `DatasetStore` | Saves a dataset and returns its revision; loads one by name and revision | `evalr.memory`, `evalr.jsonl`, `evalr.langfuse`, `evalr.hf` |
| `ScoreSink` | Records verdicts as scores, idempotently | `evalr.memory`, `evalr.langfuse`, OpenTelemetry evaluation events (phase 5) |
| `ExperimentTracker` | Runs a task over a dataset and judges each output | `evalr.memory`, `evalr.langfuse` |
| `FeedbackSource[InputT, VerdictT]` | Yields examples from people's typed feedback | `evalr.memory`; artifactr's and reflexr's `[evals]` extras |
| `Formatter[InputT]` | Renders an input as text within a token budget | `InputFormatter` (core) |

- **Compositions, not special cases.** A decision evaluator that hands unsure inputs to a language-model judge is `Fallback(DecisionEvaluator(...), DspyJudge(...))`.
- **I/O ports are async.** Adapters over synchronous SDKs run them in a worker thread.
- **Every port has an in-memory adapter** in `evalr.memory`, and a contract suite in `evalr.contracts` that the in-memory adapter and every other adapter pass. The libraries run the `FeedbackSource` suite against their own adapters.

| Package | Extra | May import |
|---|---|---|
| `evalr.core` | | pydantic, opentelemetry-api |
| `evalr.memory`, `evalr.contracts`, `evalr.jsonl` | | core |
| `evalr.dspy` | `[dspy]` | core, dspy |
| `evalr.decision` | `[jev]` | core, pydantic-ai-slim with the typesafe extra |
| `evalr.langfuse` | `[langfuse]` | core, langfuse |
| `evalr.hf` | `[hf]` | core, datasets, huggingface_hub |

Every package may also use the core's own dependencies, pydantic and the OpenTelemetry API. A test enforces the table: what each package imports, that no adapter package imports another, and that nothing imports artifactr or reflexr. The `[all]` extra installs every integration.

## Verdicts

A verdict type is any Pydantic model: an application's feedback type, a library's `Feedback` subclass, or an ad-hoc model. evalr needs nothing from the libraries ([ADR-0001](adr/0001-typed-verdicts-over-any-pydantic-model.md)).

```python
class Helpfulness(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    category: Literal["billing", "bug", "other"]
    reason: str | None = None
```

`verdict_fields(Helpfulness)` describes how each field is judged and scored. It is the one place that reads field types, and every evaluator kind, metric and integration builds on it:

| Field type | Kind | Filled by | Agreement |
|---|---|---|---|
| `bool` | binary | any evaluator | accuracy, Cohen's kappa |
| `Literal`, `Enum` | categorical | any evaluator | accuracy, Cohen's kappa |
| `int` bounded on both sides | ordinal | any evaluator | mean absolute error, Spearman |
| any other `int` or `float` | numeric | any evaluator | mean absolute error, Spearman |
| `str` | text | language-model judges only | not scored |

- `X | None` is judged as `X` and may be left empty. Bounds are read from `Field(ge=, le=, gt=, lt=)` and `annotated_types` constraints at any level of `Annotated`, including inside an optional. An integer's exclusive bounds become inclusive (`gt=0` is 1).
- A field's description is the instruction judges read for it.
- Any other type (a list, a nested model, a union of several types) raises `UnsupportedField` when an evaluator is built, rather than failing later.

An evaluator returns a `Verdict[V]`, an immutable Pydantic model:

| Field | Meaning |
|---|---|
| `value` | The verdict type's instance |
| `confidence` | The probability that each field's value is right, from 0 to 1, for the fields the evaluator has one for. Decision models report them; most judges do not. Keys must be fields of the verdict type. |
| `evaluator`, `version` | Who judged. A changed evaluator changes its version, so verdicts from before and after never mix. |
| `latency` | Wall-clock seconds the evaluation took |
| `cost` | US dollars, when known |
| `trace_id` | The OpenTelemetry trace the evaluation ran in, as 32 hex digits, when there was one |

## Evaluators

`Evaluator[InputT, VerdictT]` is a protocol: a `name`, a `version`, a `verdict_type`, and `async evaluate(input) -> Verdict[VerdictT]`. Inputs are Pydantic models too. The protocol is contravariant in the input and covariant in the verdict, so evaluators of different verdict types fit one `list[Evaluator[Thread, BaseModel]]`.

| Kind | How | Version |
|---|---|---|
| `FunctionEvaluator` | A sync or async function of the input: a deterministic measure | Given; bump it when the function changes |
| `DspyJudge` | A DSPy program whose signature comes from the input and verdict types | A hash of the program and the types |
| `DecisionEvaluator` (phase 3) | A pydantic-ai agent on a decision model | The decision model's id and its thresholds |
| `Fallback(primary, fallback, min_confidence=)` | A composition: the primary judges, and hands off to the fallback | A hash of both evaluators' names and versions, and the threshold |

An evaluator that declines an input raises `HandOff`. `Fallback` hands off when the primary raises it, or, with `min_confidence`, when any field of the primary's verdict is less confident than that. So a decision model backed by a language-model judge is `Fallback(DecisionEvaluator(...), DspyJudge(...), min_confidence=0.7)`: two adapters of one port, neither aware of the other. Each verdict records the evaluator that actually gave it, so the two are measured apart; the composition's span, `evalr.fallback {name}`, records whether and why it handed off. Any other failure propagates.

### DSPy judges

`DspyJudge(verdict_type, inputs=...)` (`evalr.dspy`, the `[dspy]` extra) is a language-model judge: a DSPy program whose signature is derived from the two types by `judge_signature`.

- **Inputs:** one text input per field of the input type, rendered by an `InputFormatter` within its token budget, described by the field's description.
- **Outputs:** one per field of the verdict type, typed as the field is (`int`, `bool`, a `Literal` or `Enum`, `float`, `str`, optionally `None`). The field's description is its instruction, with its bounds spelled out ("a whole number from 1 to 5"), since DSPy reads only the type. Input and verdict fields need distinct names, and `reasoning` is DSPy's.
- **Instructions:** "Read the {input} and judge it, giving a {verdict}", followed by the verdict type's docstring, unless given. GEPA rewrites them.
- **Program:** `dspy.Predict`, or `dspy.ChainOfThought` with `reasoning=True`. It runs with the judge's `lm`, or DSPy's configured one.
- **Validation:** the outputs are validated as the verdict type, so an out-of-range rating fails rather than passing through. An optional text field answered with "None", "null" or nothing is empty.
- **Version:** a hash of the program's state (instructions, demonstrations, fields) and of how each field of the two types is judged, described so that it is the same on every Python and pydantic version. Training changes it.
- **Cost:** DSPy reports no per-call cost, so a DSPy verdict's `cost` is unknown.

DSPy ships no type information, so `typings/dspy/` holds minimal stubs for the parts evalr uses; pyright reads them in place of the package.

### Measuring and optimizing

`measure(evaluator, dataset)` judges every labelled example and returns a `Measurement`: the verdicts and errors by example id, agreement with people, calibration, and latency and cost per evaluator version. An example the evaluator fails on, or hands off, counts as a missing prediction.

An `Optimizer[InputT, VerdictT, EvaluatorT]` fits an evaluator to people's verdicts: `optimize(evaluator, train=, validate=)` returns the fitted evaluator, with a new version if it changed, and leaves the one given alone. `optimize(evaluator, train=, validate=, optimizer=)` in the core uses only the labelled examples and refuses sets that share an example, so the validation score is honest.

| Optimizer | Fits | Package |
|---|---|---|
| `BestOf(candidates)` | Any evaluator: picks, from it and the candidates, the one that agrees best with people on `train`, and measures the choice on `validate`. A tie keeps the evaluator given. | `evalr.memory` |
| GEPA (phase 2) | A DSPy judge's instructions, from people's verdicts and their reasons | `evalr.dspy` |
| Threshold calibration (phase 3) | A decision evaluator's thresholds | `evalr.decision` |

## Datasets

An `Example[InputT, VerdictT]` is one input with what is known about it:

- `id`: stable for life, derived from the feedback or item it came from. Splits are hashed from it, and syncing uses it.
- `input`: what an evaluator judges.
- `verdict`: the verdict people gave, when there is one. Judges are trained and measured against it.
- `reference`: a reference output for the system being evaluated, as JSON, for evaluators that compare against one.
- `trace_id`: the trace the input came from, so datasets and experiments link back to it.
- `metadata`: anything else, as JSON.

A `Dataset[InputT, VerdictT]` is an immutable, named collection of examples with unique ids, and the input and verdict types they share.

- `version` is a hash of the examples' content, independent of their order. A trained judge records the version it was trained on.
- `split(validate=0.2, salt="")` sends an example to validation when `split_bucket(id, salt) < validate`, where the bucket is the first eight bytes of `sha256(salt, id)` as a fraction. So an example never moves between training and validation as others are added or removed, and raising the fraction only moves examples into validation. A different salt gives an independent split.
- `labelled()` and `filter(predicate)` select examples. `records()` and `Dataset.from_records(...)` convert to and from JSON records, which the Langfuse and Hugging Face integrations build on.

### Stores and sources

A `DatasetStore` saves a dataset under its name and returns the revision it made; `load(name, input_type=, verdict_type=, revision=None)` loads the latest revision or the one given, validating the examples as the types given, and raises `DatasetNotFound` for an unknown name or revision. Every revision stays loadable after later saves, so an experiment or a trained judge can name the exact data it used, and saving the same content again changes nothing a load can see.

| Adapter | Revision | Notes |
|---|---|---|
| `InMemoryDatasetStore` (`evalr.memory`) | The content hash | JSON records in memory, validated again on load |
| `JsonlDatasetStore(root)` (`evalr.jsonl`) | The content hash | A directory per dataset: `dataset.json` names the latest revision and holds the description; each revision is `{hash}.jsonl`, one example to a line, written whole. Names are `/`-separated segments of letters, digits, `.`, `_` and `-`, so they stay under the root. |
| Langfuse, Hugging Face (phase 4) | | |

A `FeedbackSource[InputT, VerdictT]` yields examples from people's feedback: every example has a verdict, ids are stable, and iterating again yields the same examples. artifactr's and reflexr's `[evals]` extras implement it over their logs; `InMemoryFeedbackSource` holds a fixed list. `collect(name, source)` gathers one into a dataset.

### Contract suites

`evalr.contracts` holds a check per port, which raises `ContractViolation` where an adapter differs from the port's contract. The checks need no test framework, so the libraries run `check_feedback_source` against their own adapters.

- `check_dataset_store(store)`: an unknown name is not found; a saved dataset loads back exactly (name, examples, description); saving again changes nothing; a changed dataset makes a new revision and the earlier one still loads; an unknown revision is not found; loading as a type the examples do not satisfy fails validation.
- `check_feedback_source(source)`: ids are unique, inputs and verdicts are of the source's types, every example has a verdict, and iterating again yields the same examples.
- `check_score_sink(sink, recorded)`: recording a score again replaces it, every score recorded is kept, and the latest value wins. A sink has no reads, so the caller says how to see what it holds.
- `check_evaluator(evaluator, inputs)`: each verdict is of the verdict type, names the evaluator that gave it and its version, and records the trace it was judged in (the check judges inside a trace of its own, through the OpenTelemetry API); an evaluator may hand off some inputs but must judge one; judging does not change its name or version.
- `check_optimizer(optimizer, evaluator, train=, validate=)`: the evaluator given is left alone, and the fitted one gives the same verdict type and passes `check_evaluator`.
- `check_experiment_tracker(tracker)`: one item per example in the dataset's order; a failed task leaves no output and records its error; a failed evaluator records its error while the others still judge; verdicts record the item's trace; names and the dataset version are kept.

## Scores

`scores(verdict)` turns a verdict into one `Score` per field that has a value, named `{type}.{field}`, the convention artifactr and reflexr share for feedback. The type name is the verdict type's class name in snake case (`TaskCompletion` is `task_completion`) unless one is given, such as a library's registered feedback name.

| Field kind | Score type | Value |
|---|---|---|
| binary | `BOOLEAN` | `bool` |
| ordinal, numeric | `NUMERIC` | `float` |
| categorical | `CATEGORICAL` | the choice as a string (an `Enum`'s value) |
| text | `TEXT` | the text |

- A score's id is a UUID derived from its subject (a given key, else the verdict's trace, else a hash of the verdict), the evaluator, its version and the score's name. So recording a verdict again replaces its scores, and a new evaluator version adds new ones rather than overwriting.
- The evaluator, its version and the field's confidence travel as the score's metadata.
- A `ScoreSink` records scores, idempotently by id. `InMemoryScoreSink` keeps them by id; Langfuse is phase 4, and OpenTelemetry evaluation events phase 5.

## Experiments

An experiment runs a **task** (the system being evaluated) on every example of a dataset and judges each output with every evaluator:

```python
async def reply(example: Example[Thread, Helpfulness]) -> Thread:
    return await agent_under_test.continue_thread(example.input)


result = await tracker.run_experiment(
    "prompt-v2",
    dataset=dataset,
    task=reply,
    evaluators=[judge, decider],
    metadata={"prompt": "v2"},
)
result.verdicts("helpfulness-judge")  # by example id
```

- The task receives the whole example (input, people's verdict, reference) and returns what the evaluators judge. A task that returns the example's input unchanged measures the evaluators themselves against people's verdicts.
- The result has one `ItemResult` per example in the dataset's order: the output, one verdict per evaluator that succeeded, the errors, and the item's trace. A failing task or evaluator fails only its own item.
- `InMemoryExperimentTracker` runs in the process, at most `max_concurrency` examples at once, each in a span named `evalr.experiment.item {name}`, so verdicts record the item's trace. Runs are named `{name} #{n}` unless named, and kept in `runs`. Langfuse's experiments are phase 4.

## Formatters

A formatter renders an input as the text a judge reads. A decision model's state is limited (Jev's to 32K tokens), and a language model's context costs money, so formatters work within a budget.

- `InputFormatter(max_tokens=30_000, count_tokens=estimate_tokens)` renders each field as a section headed by its name and description: strings as they are, lists one item to a line, anything else as JSON. `fields(input)` renders the fields separately, for judges that read them one by one.
- Over budget, the longest list loses its oldest items, after the first (usually the request), with a marker saying how many were omitted. Then the longest remaining text is shortened in the middle. The result always fits.
- `estimate_tokens` counts one token per three bytes of UTF-8, which overestimates English and is close for scripts of three bytes a character, so a budget measured with it is rarely exceeded. Where the limit is exact, pass the model's tokenizer as `count_tokens`.
- Summarizing, rather than windowing, is a formatter too: any callable from the input to text fits the `Formatter` protocol.

## Metrics

Agreement compares an evaluator's verdicts with people's, field by field, with the measures that suit each kind. Calibration asks whether its confidence means what it says. Every measure that is undefined for its data (no pairs; kappa when both sides always give one label; Spearman when a side never varies) is `None`, not NaN, so results compare and serialize cleanly.

| Function | Measures |
|---|---|
| `accuracy`, `cohen_kappa` | Binary and categorical fields. Kappa is agreement beyond what the two sides' label frequencies give by chance. |
| `mean_absolute_error`, `spearman` | Ordinal and numeric fields. Spearman ranks tied values by their average rank. |
| `brier_score`, `expected_calibration_error` | Confidence against correctness. A verdict's confidence is one probability per field, that its value is right, so both are top-label measures. Calibration error uses equal-width bins, closed below, the last including 1. |
| `field_agreement(expected, predicted)`, `agreement_score` | One pair of verdicts, per field and overall, from 0 to 1: binary and categorical fields agree fully or not at all; bounded numbers lose agreement in proportion to the distance over their range; unbounded ones as `1 / (1 + distance)`; a missing prediction agrees not at all. Only fields people gave a value count. This is the metric optimizers fit judges to. |
| `agreement(expected, predicted, verdict_type=)` | Per field over many pairs: `n`, `missing`, the mean per-pair `score`, and accuracy and kappa or mean absolute error and Spearman. A missing prediction counts as a wrong label for accuracy and kappa, and is left out of the error and correlation. |
| `calibration(expected, verdicts, verdict_type=)` | Per field with confidence: accuracy, mean confidence, calibration error and Brier score. |
| `evaluator_stats(verdicts)` | Per evaluator version: count, mean, median and 95th-percentile latency (nearest rank), and total and mean cost over the verdicts that report one. |

The measures over pairs are property-tested against scikit-learn and SciPy, and calibration error against a NumPy computation.

## Observability

evalr uses the OpenTelemetry API only, under the `evalr` scope, and never configures the SDK. Evaluators take an optional `tracer_provider`, defaulting to the global one.

- Every evaluation runs in a span named `evalr.evaluate {evaluator}`, with the attributes `evalr.evaluator.name`, `evalr.evaluator.version` and `evalr.verdict.type`. The span is current while the evaluator works, so the spans of the language models or agents it calls nest under it. A failure is recorded on the span.
- The verdict's `trace_id` is that span's trace, so a verdict made inside an experiment item's trace, or on the trace of the run it judges, links back to it. With no SDK configured, and no enclosing trace, it is `None`.
- `judging(tracer, evaluator=, version=, verdict_type=)` is the context manager every evaluator kind uses; application evaluators can use it too.

## Quality

The gates are those of artifactr and reflexr ([ADR-0005](adr/0005-quality-gates-and-license.md)): pyright strict with no suppressions, 100% line and branch coverage, warnings as errors, and no network in tests. Jev is tested through the TypeSafe SDK's transport, DSPy with its dummy language model, Langfuse with fakes and an in-memory span exporter, and Hugging Face with local datasets.
