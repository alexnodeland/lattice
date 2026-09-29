# API reference

The reference is generated from the library's docstrings and type annotations. It documents each package's public API: the names in its `__all__`. Anything else is internal and may change without notice.

## Packages

evalr is built as ports and adapters ([Concepts](../concepts.md#ports-and-adapters)). `evalr.core` holds the values, the pure functions over them and the ports; every other package implements or uses the ports, depends only on the core, and needs its extra where it adapts a third-party library.

| Package | What it holds | Install |
|---|---|---|
| [`evalr.core`](core.md) | Verdicts and field kinds, the ports, function evaluators and `Fallback`, examples, datasets and splits, formatters, scores, experiments' results, measuring and optimizing, the metrics, and tracing | core |
| [`evalr.memory`](memory.md) | In-memory adapters of every port, and `BestOf` | core |
| [`evalr.contracts`](contracts.md) | A contract suite per port, which every adapter passes | core |
| [`evalr.jsonl`](jsonl.md) | A dataset store on JSON Lines files | core |
| [`evalr.measures`](measures.md) | End-to-end workflow measures: task completion, drop-off and rewrites | core |
| [`evalr.online`](online.md) | Evaluators on live traffic, budgets, and OpenTelemetry evaluation events | core |
| [`evalr.dspy`](dspy.md) | DSPy judges, GEPA, and saved judges | `dspy` extra |
| [`evalr.decision`](decision.md) | Decision evaluators, the decision-only view, and threshold calibration | `jev` extra |
| [`evalr.langfuse`](langfuse.md) | Langfuse datasets, scores and experiments | `langfuse` extra |
| [`evalr.hf`](hf.md) | Hugging Face datasets: publishing, pinning and importing | `hf` extra |

## The top-level package

`evalr` re-exports the names most applications need, so `from evalr import Dataset, measure` works. Each is documented in `evalr.core`:

| Name | Documented in |
|---|---|
| `Verdict` | [`evalr.core`: Verdicts](core.md#verdicts) |
| `FieldKind`, `VerdictField`, `verdict_fields`, `UnsupportedField` | [`evalr.core`: Verdict fields](core.md#verdict-fields) |
| `Evaluator`, `FunctionEvaluator`, `Fallback`, `HandOff` | [`evalr.core`: Evaluators](core.md#evaluators) |
| `Example`, `Dataset`, `DatasetStore`, `DatasetNotFound`, `FeedbackSource`, `collect` | [`evalr.core`: Examples and datasets](core.md#examples-and-datasets) |
| `InputFormatter` | [`evalr.core`: Formatters](core.md#formatters) |
| `Score`, `ScoreSink`, `scores` | [`evalr.core`: Scores](core.md#scores) |
| `ExperimentTracker`, `ExperimentResult` | [`evalr.core`: Experiments](core.md#experiments) |
| `measure`, `Optimizer`, `optimize` | [`evalr.core`: Measuring and optimizing](core.md#measuring-and-optimizing) |
| `agreement`, `Agreement`, `calibration`, `evaluator_stats` | [`evalr.core`: Metrics](core.md#metrics) |

`evalr.__version__` is the installed version.
