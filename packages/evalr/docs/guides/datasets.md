# Datasets, splits and stores

Judges are trained on people's verdicts and measured against them, so evalr's datasets are collections of inputs with the verdicts people gave. They are immutable and versioned by their content, split deterministically, and saved to stores that keep every revision: in memory, as JSON Lines files, in Langfuse, or on the Hugging Face Hub ([ADR-0003](../adr/0003-datasets-and-experiments-in-langfuse-and-hugging-face.md)).

The examples on this page use the `Thread` and `Helpfulness` types from [Getting started](../getting-started.md#1-define-the-types).

## Examples

An `Example` is one input with what is known about it:

| Field | Holds |
|---|---|
| `id` | A stable identifier, for life. Splits are hashed from it and stores key items by it, so derive it from the feedback or item the example came from. |
| `input` | What an evaluator judges: a thread, a run, an artifact version |
| `verdict` | The verdict people gave, when there is one |
| `reference` | A reference output for the system being evaluated, as JSON, for evaluators that compare against one |
| `trace_id` | The trace the input came from, so datasets and experiments link back to it |
| `metadata` | Anything else, as JSON |

```python
from evalr import Dataset, Example

examples = [
    Example[Thread, Helpfulness](
        id="fb_0192",
        input=Thread(request="I was charged twice", reply="I refunded the duplicate charge."),
        verdict=Helpfulness(rating=5, resolved=True, reason="Fixed at once"),
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
    ),
    Example[Thread, Helpfulness](
        id="fb_0193",
        input=Thread(request="My order is late", reply="Orders arrive within a week."),
        verdict=Helpfulness(rating=2, resolved=False, reason="It ignored my order"),
    ),
    Example[Thread, Helpfulness](
        id="fb_0194",
        input=Thread(request="Cancel my plan", reply="Done: your plan ends today."),
    ),
]
```

## Datasets

A `Dataset` is an immutable, named collection of examples with unique ids, and the input and verdict types they share:

```python
support = Dataset(
    "acme/helpfulness",
    examples,
    input_type=Thread,
    verdict_type=Helpfulness,
    description="People's ratings of support replies",
)
print(len(support), "fb_0192" in support, len(support.labelled()))
print(support.version)
```

```text
3 True 2
180e6a296f478c0f
```

- **`version`** is a hash of the examples' content, independent of their order. Any change to any example changes it, so a trained judge records exactly the data it was trained on.
- **Ids are unique**: two examples with one id raise `DuplicateExample`. A verdict type evalr cannot judge raises `UnsupportedField`.
- **`labelled()`** keeps the examples with a verdict from people, and **`filter(predicate)`** any others you choose. Both return a dataset of the same name and types.
- **`records()`** turns the examples into JSON records, and **`Dataset.from_records(name, records, input_type=, verdict_type=)`** back. The stores build on them.

## Splits

`split(validate)` divides a dataset into training and validation examples, deterministically:

```python
train, validate = support.labelled().split(0.2)
```

An example goes to validation when `split_bucket(id, salt)`, a hash of its id placed between 0 and 1, is below the fraction. So:

- an example never moves between training and validation as other examples are added or removed, and a judge's validation score stays honest as a dataset grows
- raising the fraction only moves examples from training into validation
- the split is the same in every process and on every machine
- `split(0.2, salt="round-2")` gives an independent split of the same examples

The fraction is an expected share: on a small dataset, the validation set can be larger or smaller than it suggests, or empty.

## Stores

A `DatasetStore` saves a dataset under its name and returns the revision it made; `load` reads the latest revision, or the one you name, and validates the examples as the types you give:

```python
from evalr.memory import InMemoryDatasetStore

store = InMemoryDatasetStore()
revision = await store.save(support)

loaded = await store.load("acme/helpfulness", input_type=Thread, verdict_type=Helpfulness)
pinned = await store.load(
    "acme/helpfulness", input_type=Thread, verdict_type=Helpfulness, revision=revision
)
```

Every store keeps the same promises, which the [contract suite](testing.md#your-own-adapters) checks:

- Every revision stays loadable after later saves, so an experiment or a trained judge can name the exact data it used.
- Saving the same content again changes nothing a load can see.
- An unknown name or revision raises `DatasetNotFound`, and examples that are not of the types given raise `pydantic.ValidationError`.

| Store | Package | Revision | For |
|---|---|---|---|
| `InMemoryDatasetStore` | `evalr.memory` | The content hash | Tests and prototypes |
| `JsonlDatasetStore(root)` | `evalr.jsonl` | The content hash | Files in a repository or on a disk |
| `LangfuseDatasetStore(client)` | `evalr.langfuse` | The time of the save's latest change | Working datasets, beside the traces they came from |
| `HfDatasetStore(api)` | `evalr.hf` | The commit's hash | Published and pinned datasets |

### JSON Lines files

`JsonlDatasetStore` keeps each dataset in a directory under its root, named by the dataset (`acme/helpfulness` becomes `acme/helpfulness/`). Each revision is a JSON Lines file named by the content hash, one example to a line, written whole so a reader never sees half of one. `dataset.json` names the latest revision and holds the description:

```python
from evalr.jsonl import JsonlDatasetStore

files = JsonlDatasetStore("datasets")
revision = await files.save(support)
```

```text
datasets/
  acme/
    helpfulness/
      dataset.json              {"description": "...", "latest": "180e6a296f478c0f"}
      180e6a296f478c0f.jsonl    one example to a line
```

Names are `/`-separated segments of letters, digits, `.`, `_` and `-`, so a dataset can never be read or written outside the root. The files are plain JSON Lines, readable by any tool, including Hugging Face's `load_dataset("json", data_files=...)`.

### Langfuse datasets

Langfuse holds working datasets beside the traces they came from. `LangfuseDatasetStore` saves a dataset as a Langfuse dataset of the same name, with an item per example, through your own Langfuse client. It needs the `langfuse` extra:

```python
from langfuse import Langfuse

from evalr.langfuse import LangfuseDatasetStore

langfuse = Langfuse()  # configured from LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
datasets = LangfuseDatasetStore(langfuse)

revision = await datasets.save(support)
as_saved = await datasets.load(
    "acme/helpfulness", input_type=Thread, verdict_type=Helpfulness, revision=revision
)
```

| Item | Holds |
|---|---|
| id | A UUID 5 of the dataset's name and the example's id (`item_id`), so saving again updates items rather than adding more |
| input | The example's input |
| expected output | `{"verdict": ..., "reference": ...}` |
| metadata | The example's metadata, with its id under `evalr` |
| source trace | The example's `trace_id`, linking the item to the trace it came from |

- **Only changed items are written.** Examples no longer in the dataset are archived, not deleted.
- **A revision is a time.** Langfuse versions a dataset's items by time, so `save` returns the time of the latest change it made, in ISO 8601, and loading that revision reads the items as they were then.
- **Items made in Langfuse load too**, with their input as the input and their expected output as the verdict, so a dataset people curated in Langfuse's UI can train a judge.
- The client's calls are synchronous, so they run in a worker thread. The store makes no connection of its own.

### The Hugging Face Hub

The Hub holds published and pinned datasets. `HfDatasetStore` saves a dataset as a dataset repository of the same name (`acme/helpfulness`), each save one commit of the examples (`data/train.jsonl`) and a dataset card (`README.md`). It needs the `hf` extra:

```python
from evalr.hf import HfDatasetStore

hub = HfDatasetStore()  # HfApi(), with the token the Hugging Face tools find
commit = await hub.save(support)
at_commit = await hub.load(
    "acme/helpfulness", input_type=Thread, verdict_type=Helpfulness, revision=commit
)
```

- **A revision is the commit's hash**, so it names the data exactly, forever. `load` also takes a branch or a tag.
- **New repositories are private** unless you pass `private=False`.
- **The card** points the Hub's dataset viewer and `datasets.load_dataset` at the examples, and records the types, the description and the content hash under `evalr`. Its body describes the dataset, its size and its verdict fields.

To **import** any dataset on the Hub, pin it first: only a full commit hash names the same data every time, so `import_dataset` accepts nothing else. `resolve_revision` pins a branch or a tag to its commit. Rows are read as evalr's records, or through a function of your own:

```python
from typing import Any

from evalr.hf import import_dataset, resolve_revision

commit = resolve_revision("acme/support-threads", "v1")  # a tag, pinned to its commit


def to_example(row: dict[str, Any]) -> Example[Thread, Helpfulness]:
    return Example[Thread, Helpfulness](
        id=row["id"],
        input=Thread(request=row["question"], reply=row["answer"]),
        verdict=Helpfulness(rating=row["stars"], resolved=row["solved"]),
    )


threads = await import_dataset(
    "acme/support-threads",
    revision=commit,
    input_type=Thread,
    verdict_type=Helpfulness,
    to_example=to_example,
)
```

`import_dataset` reads through `datasets.load_dataset`, so it takes a local directory of data files as well as a repository, with `split=`, `cache_dir=` and `token=` for private datasets.

The store reaches the Hub through `HubApi`, a narrow protocol that `huggingface_hub.HfApi` satisfies, so a test can pass a fake of it.

## Datasets from feedback

The examples usually come from people's feedback, recorded by your application. A [feedback source](feedback-sources.md) yields them, and `collect` gathers them into a dataset.
