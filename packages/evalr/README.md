# evalr

A Python library for **typed evaluation of agent systems**. An evaluator judges an input (a chat thread, a workflow run, an artifact version) and returns a verdict: an instance of a Pydantic type, typically one of the feedback types people also give. Because people and evaluators produce the same types, evaluators can be trained on people's feedback and measured against it.

Two kinds of evaluator are equals: [DSPy](https://dspy.ai) judges optimized with GEPA, and TypeSafe's Jev decision models through [pydantic-ai](https://ai.pydantic.dev), with a language-model fallback. Datasets and experiments live in [Langfuse](https://langfuse.com) and on the [Hugging Face Hub](https://huggingface.co/datasets).

> **Status:** pre-release. evalr is being built in the phases tracked by [RFC-0001](docs/rfcs/0001-v0.1-implementation-plan.md).

Part of a family with [artifactr](https://github.com/alexnodeland/artifactr) and [reflexr](https://github.com/alexnodeland/reflexr), which depend on evalr through their `[evals]` extras. evalr imports neither.

## Install

```bash
uv add evalr                 # the core: verdicts, evaluators, datasets, metrics
uv add "evalr[dspy]"         # DSPy judges and GEPA
uv add "evalr[jev]"          # decision evaluators on TypeSafe's Jev
uv add "evalr[langfuse]"     # dataset sync, experiments and scores in Langfuse
uv add "evalr[hf]"           # Hugging Face import and export
uv add "evalr[all]"          # everything
```

## Documentation

- [Architecture](docs/architecture.md): concepts, packages and what exists today.
- [Architecture decision records](docs/adr/README.md): why each part is the way it is.
- [RFCs](docs/rfcs/README.md): proposals and the v0.1 build plan.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](LICENSE)
