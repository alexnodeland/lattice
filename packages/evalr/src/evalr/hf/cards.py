"""Dataset cards: what a dataset on the Hugging Face Hub is, for people and for evalr."""

import json
from typing import Any, cast

from huggingface_hub import DatasetCard
from pydantic import BaseModel

from evalr.core import Dataset, verdict_fields

__all__ = ["DATA_FILE", "dataset_card", "read_card"]

DATA_FILE = "data/train.jsonl"
"""Where a dataset's examples are, one JSON record to a line."""


def dataset_card[InputT: BaseModel, VerdictT: BaseModel](dataset: Dataset[InputT, VerdictT]) -> str:
    """The README of a dataset on the Hub: metadata for evalr and the Hub, and a description.

    The metadata points the Hub's viewer and ``datasets.load_dataset`` at the examples, and
    records the types, the description and the content hash under ``evalr``.
    """
    metadata = {
        "pretty_name": dataset.name,
        "tags": ["evalr"],
        "configs": [
            {"config_name": "default", "data_files": [{"split": "train", "path": DATA_FILE}]}
        ],
        "evalr": {
            "format": 1,
            "input_type": dataset.input_type.__name__,
            "verdict_type": dataset.verdict_type.__name__,
            "version": dataset.version,
            "description": dataset.description,
        },
    }
    rows = "\n".join(
        f"| `{f.name}` | {f.kind.value} | {f.description or ''} |"
        for f in verdict_fields(dataset.verdict_type)
    )
    body = f"""# {dataset.name}

{dataset.description or "An evaluation dataset."}

Made with [evalr](https://lattice.alexnodeland.com/evalr/): each example is an input
(`{dataset.input_type.__name__}`) with the verdict people gave it
(`{dataset.verdict_type.__name__}`), a reference output, or both.

| | |
|---|---|
| Examples | {len(dataset)}, {len(dataset.labelled())} with a verdict |
| Version | `{dataset.version}`, a hash of the examples' content |
| Data | `{DATA_FILE}`, one example to a line |

## Verdict fields

| Field | Kind | Description |
|---|---|---|
{rows}
"""
    # JSON is YAML, so the front matter needs no YAML writer.
    front = json.dumps(metadata, indent=2, ensure_ascii=False)
    return f"---\n{front}\n---\n\n{body}"


def read_card(text: str) -> dict[str, Any]:
    """What a card records under ``evalr``; empty for a card evalr did not write."""
    metadata: dict[str, Any] = DatasetCard(text).data.to_dict()
    ours: object = metadata.get("evalr")
    return dict(cast(dict[str, Any], ours)) if isinstance(ours, dict) else {}
