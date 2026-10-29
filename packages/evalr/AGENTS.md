# AGENTS.md: evalr

Root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to evalr.

evalr is typed evaluation of agent systems: an evaluator judges an input and returns a verdict, an instance of a Pydantic type, usually the same feedback type people give. DSPy judges are trained on people's feedback with GEPA, Jev decision models sit in front of them, and datasets and experiments live in Langfuse or Hugging Face. See [the architecture](../../docs/evalr/architecture.md).

## Layout

- `src/evalr/core/`: the ports and the pure model (verdicts, datasets, evaluators, `Fallback`, metrics). Depends only on pydantic, annotated-types and the OpenTelemetry API.
- `src/evalr/memory/`, `jsonl/`: in-process and file adapters.
- `src/evalr/contracts/`: the port contracts (`check_evaluator`, `check_optimizer`, ...) every adapter must pass.
- `src/evalr/dspy/`, `decision/`, `langfuse/`, `hf/`: adapters behind the `dspy`, `jev`, `langfuse` and `hf` extras.
- `src/evalr/measures/`, `online/`: measures and online evaluation.
- `typings/`: hand-written stubs for `dspy` and `datasets`, which ship none. Edit them when pyright needs a name they lack.
- `tests/<layer>/`: one directory per layer; `tests/contracts/` runs every adapter through its port's contract.

## Commands

```bash
moon run evalr:test           # pytest with the 100% branch-coverage gate
moon run evalr:check          # lint, typecheck, test, standalone, deptry
moon run evalr:format
uv run pytest packages/evalr/tests/core/test_metrics.py -n0
```

evalr has no `schema`, `pg-up` or database tasks, and no generated files. It depends on no other lattice project.

## Layering

`tests/test_layering.py` enforces it:

- `core` imports only itself, pydantic, opentelemetry and annotated-types.
- Every other package imports only `evalr.core`, itself, and its own third-party dependency (`dspy`, `pydantic_ai`, `langfuse`, `datasets`/`huggingface_hub`). Adapters never import each other.
- Nothing in evalr imports `artifactr` or `reflexr`; they depend on evalr, not the reverse.
- A new package under `src/evalr/` needs an entry in `LAYERS`, or the test fails.

## Conventions

- A new adapter of a port passes that port's checks in `evalr.contracts`; add it to the matching `tests/contracts/` test.
- Tests make no network calls: DSPy runs on scripted LMs (`tests/dspy/scripted.py`), Langfuse on a local fake (`tests/langfuse/server.py`), Hugging Face offline (`tests/hf/conftest.py`).
- Metrics are property-tested against scipy and scikit-learn (test-only dependencies); keep new metrics checked the same way.
- Trained judges are saved as JSON files ([ADR-0007](../../docs/evalr/adr/0007-trained-judges-saved-as-json-files.md)).

## Key ADRs

- [ADR-0001](../../docs/evalr/adr/0001-typed-verdicts-over-any-pydantic-model.md): typed verdicts over any Pydantic model.
- [ADR-0002](../../docs/evalr/adr/0002-dspy-judges-and-decision-models-as-equals.md): DSPy judges and decision models as equals.
- [ADR-0006](../../docs/evalr/adr/0006-ports-and-adapters.md): ports and adapters.
- [ADR-0008](../../docs/evalr/adr/0008-decision-only-views-and-hand-off-by-composition.md): hand-off by composition (`Fallback`).
- [ADR-0011](../../docs/evalr/adr/0011-scores-shared-with-the-libraries.md), [ADR-0012](../../docs/evalr/adr/0012-langfuse-score-adapters-in-evalr.md): scores shared with the libraries, and their Langfuse adapters here.

## Pitfalls

- Warnings are errors; the one filter in `pyproject.toml` covers `backoff` under Langfuse. Don't widen it to hide a new warning.
- An import of an extra's package in `core` breaks the bare install that `evalr:standalone` checks.
