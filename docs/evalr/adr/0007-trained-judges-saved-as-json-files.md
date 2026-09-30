# ADR-0007: Trained judges saved as JSON files

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

RFC-0001 left open where trained judges live: files in the application's repository, the Hugging Face Hub, or Langfuse's prompt management. It settled v0.1 on files, and required that a trained judge be versioned: its compiled program is saved with the dataset version it was trained on, its scores and the optimizer's settings, and its version is a hash of the program.

Two further questions came up while building it:

- **Format.** DSPy can save a program's state as JSON, or the whole program with cloudpickle. Loading a pickle executes code from the file.
- **Drift.** A saved program is only meaningful with the input and verdict types it was trained between. If a field is added or its bounds change, the program no longer matches its signature.

## Decision

- **A trained DSPy judge is one JSON file**, in the format `evalr.dspy.judge/1`:

  | Key | Holds |
  |---|---|
  | `format` | `evalr.dspy.judge/1` |
  | `name`, `version` | The judge's name, and its version: a hash of the program and the types |
  | `input_type`, `verdict_type` | The types' names, for the error message when they are loaded as other types |
  | `reasoning` | Whether the program thinks step by step (`ChainOfThought`) |
  | `program` | DSPy's JSON state of the program: instructions, demonstrations, fields |
  | `training` | The `Training` record: optimizer and settings, the version it started from, the training and validation datasets (name, content hash, size), and agreement before and after |
  | `dependencies` | The DSPy and evalr versions that saved it |

- **Loading takes the types from the caller**, rebuilds the signature from them, loads the program's state, and recomputes the version. If it differs from the saved version, the types have changed since training, and loading fails rather than running a program against a signature it was not trained for.
- **No pickles, and no language models from the file.** The program is loaded from JSON only, and any language-model configuration in the state is dropped: the application supplies the model, so a saved judge cannot send requests somewhere the application did not configure.
- **Applications keep the files in their repositories**, reviewed and versioned with the code that uses them. The judge's content is one JSON document (`snapshot()`), so a store port for the Hugging Face Hub or Langfuse can be added later without changing the format.

## Options considered

### Where judges live

| Option | Reviewable | Needs a service | Versioned |
|---|---|---|---|
| **Files in the application's repository (chosen)** | In pull requests | No | By git, and by the version hash |
| The Hugging Face Hub | On the Hub | Yes | By revision |
| Langfuse's prompt management | In Langfuse | Yes | By prompt version |

### Format

| Option | Safe to load | Portable across DSPy versions |
|---|---|---|
| **DSPy's JSON state, with the types from code (chosen)** | Yes | As far as the state format is stable |
| DSPy's whole-program cloudpickle | No: loading runs code | No |

## Consequences

- Easier: a trained judge is reviewed like code, and its training is explained in the same file.
- Easier: loading can never execute code or pick a model from the file.
- Harder: changing a verdict type invalidates saved judges, which must be retrained. This is intended: a judge trained for one type should not silently judge another.
- Revisit: a judge-store port, once judges are shared through the Hub or Langfuse.

## Action items

1. [x] Implement `DspyJudge.snapshot`, `save` and `load` (RFC-0001 phase 2).
