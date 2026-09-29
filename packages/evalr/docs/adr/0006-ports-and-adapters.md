# ADR-0006: Ports and adapters

**Status:** Accepted, amended by [ADR-0011](0011-scores-shared-with-the-libraries.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

evalr brings together several systems that change at different speeds and that not every application uses:

- two kinds of evaluator, honoured equally ([ADR-0002](0002-dspy-judges-and-decision-models-as-equals.md)): DSPy judges and decision models (TypeSafe's Jev, through pydantic-ai)
- two ways of fitting them to people's feedback: GEPA, and threshold calibration
- two stores for datasets and experiments ([ADR-0003](0003-datasets-and-experiments-in-langfuse-and-hugging-face.md)): Langfuse and the Hugging Face Hub
- the libraries whose feedback evalr learns from, artifactr and reflexr, which depend on evalr through their `[evals]` extras and must never be imported by it ([ADR-0001](0001-typed-verdicts-over-any-pydantic-model.md))

If the core called these systems directly, every change to one would ripple through the rest, a new store or evaluator would mean editing the core, and the core could not be tested without them. The siblings keep the same boundaries: a pure core, storage behind a protocol, and in-memory implementations checked by the same behaviour suite as the real ones.

## Decision

evalr is built as **ports and adapters**.

- **`evalr.core` is the hexagon.** It holds the values (verdicts, examples, datasets, scores, experiment results), the pure functions over them (field kinds, splits, formatters, agreement and calibration metrics), and the **ports**: small `typing.Protocol`s that say what the core needs from the outside. It depends on pydantic and the OpenTelemetry API only, and imports none of dspy, pydantic-ai, typesafe-sdk, langfuse, datasets or huggingface_hub.
- **Adapters implement ports**, each in its own package, behind its own extra where it needs a third-party library. An adapter depends inward only: on `evalr.core` and its own libraries, never on another adapter package. Ports speak the core's values, never an adapter's types.
- **Compositions are assembled from ports, not special cases.** A decision evaluator that hands unsure inputs to a language-model judge is `Fallback(DecisionEvaluator(...), DspyJudge(...))`: two adapters of one port, composed by the core's `Fallback`. The decision adapter reports that it declines an input by raising the core's `HandOff`, or by low confidence.
- **I/O ports are async**, like `Evaluator`, because their callers are async servers and experiment runners. Adapters over synchronous SDKs run them in a worker thread. Pure mappings (a verdict to its scores) stay synchronous.
- **Every port has an in-memory adapter** in `evalr.memory`, usable in any application's tests. **A contract suite** for each port runs against the in-memory adapter and every other adapter, with network adapters behind the SDKs' own transports and fakes. The suites ship in `evalr.contracts`, so the libraries that implement `FeedbackSource` can run them too.
- **A test enforces the layering**: which packages each package may import, that no adapter package imports another, and that nothing in evalr imports artifactr or reflexr.

### Ports

| Port | What it does | Adapters |
|---|---|---|
| `Evaluator[InputT, VerdictT]` | Judges an input and returns a typed verdict | `FunctionEvaluator` (core), `DspyJudge` (`evalr.dspy`), `DecisionEvaluator` (`evalr.decision`); compositions: `Fallback` (core), sampling and budgets (phase 5) |
| `Optimizer[InputT, VerdictT, EvaluatorT]` | Fits an evaluator to people's verdicts on a training set, checked on a validation set | GEPA (`evalr.dspy`), threshold calibration (`evalr.decision`), in-memory (`evalr.memory`) |
| `DatasetStore` | Saves a dataset and returns its revision; loads one by name and revision | in-memory (`evalr.memory`), JSON Lines files (`evalr.jsonl`), Langfuse datasets (`evalr.langfuse`), the Hugging Face Hub (`evalr.hf`) |
| `ScoreSink` | Records verdicts as scores, idempotently | in-memory (`evalr.memory`), Langfuse scores (`evalr.langfuse`), OpenTelemetry evaluation events (phase 5) |
| `ExperimentTracker` | Runs a task over a dataset and judges each output | in-memory (`evalr.memory`), Langfuse experiments (`evalr.langfuse`) |
| `FeedbackSource[InputT, VerdictT]` | Yields examples from people's typed feedback | in-memory (`evalr.memory`); artifactr's and reflexr's `[evals]` extras |
| `Formatter[InputT]` | Renders an input as text within a token budget | `InputFormatter` (core) |

Trained judges are saved as files in v0.1, by the DSPy adapter. A port for storing them elsewhere (the Hugging Face Hub, Langfuse's prompt management) is deferred until there is a second place to store them; ADR-0007 records the file format.

### Packages

| Package | Extra | May import |
|---|---|---|
| `evalr.core` | | pydantic, opentelemetry-api |
| `evalr.memory` | | core |
| `evalr.contracts` | | core |
| `evalr.jsonl` | | core |
| `evalr.dspy` | `[dspy]` | core, dspy |
| `evalr.decision` | `[jev]` | core, pydantic-ai-slim with the typesafe extra |
| `evalr.langfuse` | `[langfuse]` | core, langfuse |
| `evalr.hf` | `[hf]` | core, datasets, huggingface_hub |

`evalr.decision` keeps the name RFC-0001 gives it. It adapts pydantic-ai's decision models, with TypeSafe's Jev behind them; `evalr.typesafe` was considered, but the adapter depends on pydantic-ai's decision-model interface rather than on TypeSafe's SDK, and any decision model pydantic-ai supports would fit it.

## Options considered

### Option A: Ports and adapters (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a protocol and an in-memory adapter per port |
| Coupling | Low: adapters meet only at the core's values |
| Testability | High: the core and every composition run on in-memory adapters, and a contract suite pins each port |
| Cost of a new store or evaluator | A new adapter package; the core is unchanged |

**Pros:** each integration can change, or be left uninstalled, without touching the others; the libraries depend on small protocols rather than on evalr's internals; contract suites catch an adapter that drifts.
**Cons:** more types; an integration's richer features must be reached through its adapter, not the port.

### Option B: Integration modules that call each other

| Dimension | Assessment |
|---|---|
| Complexity | Low at first |
| Coupling | High: experiments call Langfuse, judges call datasets |
| Testability | Each integration needs the others' fakes |
| Cost of a new store or evaluator | Edits across modules |

**Pros:** fewer types; direct access to every SDK feature.
**Cons:** the coupling ADR-0001 and ADR-0003 were written to avoid; a second store means rewriting the first's callers.

### Option C: Adopt one integration's abstractions as the core (Langfuse's experiments and evaluators)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Coupling | To one vendor's API |
| Testability | Through that vendor's fakes |
| Cost of a new store or evaluator | High for anything that is not Langfuse |

**Pros:** no translation layer for the common case.
**Cons:** evaluators would be untyped functions; Hugging Face and in-memory runs become second-class.

## Trade-off analysis

evalr is small, but it sits between four external systems and two libraries that evolve independently. The extra types of Option A buy isolation where it is needed most: an SDK upgrade touches one adapter, a new store is a new package, and every behaviour a port promises is checked the same way for every adapter. The siblings made the same trade for storage, and their behaviour suites are the precedent for evalr's contract suites.

## Consequences

- Easier: DSPy judges and decision models are interchangeable wherever an evaluator is expected, and compose (`Fallback`) without either knowing about the other.
- Easier: an application or a sibling library tests its evaluation code against `evalr.memory`, and checks its own `FeedbackSource` with `evalr.contracts`.
- Harder: a port's contract must hold for every adapter, so a port offers what all of them can do; an adapter can offer more on its own class.
- Revisit: a judge-store port, once trained judges are stored somewhere other than files.

## Action items

1. [x] Add the ports, `evalr.memory`, `evalr.jsonl`, `evalr.contracts`, `Fallback` and the layering rules (RFC-0001 phase 1).
2. [x] Implement the DSPy adapters: `DspyJudge` and GEPA (phase 2).
3. [x] Implement the decision adapters: `DecisionEvaluator` and threshold calibration (phase 3).
4. [x] Implement the Langfuse and Hugging Face adapters (phase 4).
