# DSPy judges and GEPA

A DSPy judge is a language-model evaluator: a [DSPy](https://dspy.ai) program that reads an input and gives a typed verdict. It is slower and costlier than a decision model, but it can explain itself in free text, and it can be trained on people's feedback with GEPA, DSPy's reflective optimizer, which learns from the reasons people gave ([ADR-0002](../adr/0002-dspy-judges-and-decision-models-as-equals.md)).

It needs the `dspy` extra. The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types).

## A judge from its types

```python
import dspy

from evalr.dspy import DspyJudge

judge = DspyJudge(Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini"))

verdict = await judge.evaluate(
    Thread(request="I was charged twice", reply="I refunded the duplicate charge.")
)
print(verdict.value)
```

It prints the judge's verdict, such as:

```text
rating=4 resolved=True reason='It fixed the problem'
```

- `lm` is any DSPy language model. Without one, the judge uses DSPy's configured model (`dspy.configure(lm=...)`), so one setting can serve every judge.
- `reasoning=True` makes the program think step by step before it answers (DSPy's `ChainOfThought` instead of `Predict`).
- The judge is named `{verdict type}-judge` in snake case (`helpfulness-judge`) unless you pass `name=`.
- Every verdict is validated as the verdict type, so an answer out of range (a rating of 9) raises `pydantic.ValidationError` rather than passing through. An optional text field answered with "None", "null" or nothing is left empty.
- DSPy reports no cost per call, so a DSPy verdict's `cost` is `None`, and it has no `confidence`.

### The signature

A DSPy program is defined by its signature: its input fields, its output fields and its instructions. `DspyJudge` derives it from the two types with `judge_signature`, so a judge needs no prompt of its own:

- **One input per field of the input type**, as text, described by the field's description.
- **One output per field of the verdict type**, typed as the field is (`int`, `bool`, a `Literal` or `Enum`, `float`, `str`, optionally `None`). DSPy reads only the type, so the field's description is extended with what the type means: `rating` above is described as "How much the reply helped (a whole number from 1 to 5)", and `reason` as "Why, in a sentence (may be left empty)".
- **Instructions**, unless you pass `instructions=`: "Read the Thread and judge it, giving a Helpfulness.", followed by the verdict type's docstring. GEPA rewrites them.

```python
print(judge.instructions)
```

```text
Read the Thread and judge it, giving a Helpfulness.

Whether the reply helped the person.
```

The input and verdict types need distinct field names, since each becomes a field of one signature, and `reasoning` is DSPy's own. A clash raises `ValueError` when the judge is built.

### Versions

A judge's version is a hash of its program (instructions, demonstrations and fields) and of how each field of the two types is judged. Training changes the program, so a trained judge has a new version; so does a change to either type. Verdicts record it, so scores from an untrained and a trained judge never mix.

## What a judge reads

An input is a Pydantic model, and a judge reads it as text. A formatter renders it within a token budget, because a language model's context costs money and a decision model's is limited (Jev's to 32K tokens). `DspyJudge` uses an `InputFormatter`, which renders each field of the input as one of the signature's inputs:

- Strings are used as they are, lists one item to a line, and anything else as JSON.
- When the whole is over budget, the longest list loses its oldest items first, keeping the first (usually the request) and marking how many were left out. Only if that is not enough is the longest remaining text shortened in the middle, so a list that windowing alone can fit is never also cut. The result always fits.
- Tokens are estimated as one per three bytes of UTF-8 (`estimate_tokens`), which overestimates English, so a budget measured this way is rarely exceeded. Where the limit is exact, pass the model's tokenizer.

```python
from evalr.core import InputFormatter

judge = DspyJudge(
    Helpfulness,
    inputs=Thread,
    lm=dspy.LM("openai/gpt-5-mini"),
    formatter=InputFormatter(max_tokens=8_000),
)
```

`InputFormatter(max_tokens=30_000)` is the default. A `DspyJudge` needs an `InputFormatter`, because it reads the input field by field; a [decision evaluator](decision-evaluators.md#the-state-it-reads) takes any callable from the input to text, such as a summarizer.

## Training with GEPA

An untrained judge knows only its signature. GEPA trains its instructions on people's verdicts: it runs the judge on training examples, shows a reflection model where the judge disagreed with people and why, and has it rewrite the instructions. A rewrite is kept only if it agrees better with people on the validation examples.

```python
from evalr import optimize
from evalr.dspy import Gepa

train, validate = dataset.labelled().split(0.3)

trained = await optimize(
    judge,
    train=train,
    validate=validate,
    optimizer=Gepa(reflection_lm=dspy.LM("openai/gpt-5"), auto="light"),
)
```

`dataset` is a [dataset](datasets.md) of threads with people's `Helpfulness` verdicts. `optimize` uses only the labelled examples, and refuses a training and validation set that share an example, so the validation score is honest. It also refuses a set with no labelled examples, which the [split](datasets.md#splits) of a small dataset can leave: until there are enough to split, [measure](metrics.md#measuring-an-evaluator) the judge on them all instead.

- **The metric** is per-field agreement with people, from 0 to 1: the mean of [`field_agreement`](metrics.md#one-pair-of-verdicts). An answer that is not a valid verdict scores 0.
- **The feedback** GEPA's reflection model reads names each field the judge got wrong, with both answers ("rating: you said 2, people said 4."), and quotes people's text fields ("People's reason: the refund took a week"), so it learns why people judged as they did. Give your verdict types a reason field, and ask people to fill it.
- **The budget** is one of `auto` (`"light"`, `"medium"` or `"heavy"`; `"light"` by default), `max_metric_calls` or `max_full_evals`. `reflection_minibatch_size`, `use_merge` and `seed` pass through to GEPA.
- **The reflection model** reads the judge's mistakes and rewrites its instructions. It is usually a stronger model than the judge's.
- **DSPy runs single-threaded** (`num_threads=1`), so evaluation spans keep their trace context and a seed reproduces a run. The compile runs in a worker thread, off the event loop.

The judge you started from is unchanged. The trained judge has the new program, its own version, and a `Training` record: the optimizer and its settings, the version it started from, the training and validation data (each a `DatasetRef` of name, content hash and size), and GEPA's validation scores for the starting program and the chosen one.

To check a trained judge the same way you would any evaluator, [measure it](metrics.md#measuring-an-evaluator) on examples it was not trained on.

## Saving and loading

A trained judge is one JSON file ([ADR-0007](../adr/0007-trained-judges-saved-as-json-files.md)). Keep it in your repository, next to the code that uses it, and review it like code:

```python
trained.save("helpfulness-judge.json")

judge = DspyJudge.load(
    "helpfulness-judge.json", Helpfulness, inputs=Thread, lm=dspy.LM("openai/gpt-5-mini")
)
```

The file holds the judge's name and version, its types' names, whether it reasons, DSPy's JSON state of the program, the `Training` record, and the DSPy and evalr versions that saved it. Abridged:

```json
{
  "format": "evalr.dspy.judge/1",
  "name": "helpfulness-judge",
  "version": "fc90dfc578eb",
  "input_type": "Thread",
  "verdict_type": "Helpfulness",
  "reasoning": false,
  "program": {"...": "DSPy's state: instructions, demonstrations, fields"},
  "training": {"optimizer": "gepa", "base_version": "4212cabdd66e", "...": "..."},
  "dependencies": {"dspy": "3.4.0", "evalr": "0.1.0.dev0"}
}
```

- **Loading takes the types from your code.** It derives the signature from them, loads the program's state, and recomputes the version. If either type has changed since the judge was trained, the version differs and loading raises `JudgeMismatch`: retrain the judge rather than run it against a signature it was not trained for.
- **Nothing in the file can run code or choose a model.** The state is JSON, never a pickle, and any language-model configuration in it is dropped, so the judge uses the `lm` you pass, or DSPy's configured one.
- `snapshot()` returns the same document as a `SavedJudge` model, and `DspyJudge.restore(saved, ...)` rebuilds a judge from one, for storing judges somewhere other than files.

## Tracing a judge

Each evaluation runs in an `evalr.evaluate {judge}` span, which is current while DSPy calls the model. evalr does not instrument DSPy itself: to see the model calls under that span, install and enable OpenInference's `DSPyInstrumentor` (`openinference-instrumentation-dspy`). See [the architecture's notes on observability](../architecture.md#observability) for DSPy's engines and LiteLLM.
