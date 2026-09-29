"""Hugging Face datasets: publishing, pinning and importing (the ``[hf]`` extra).

The Hugging Face Hub holds published and pinned datasets (ADR-0003). ``HfDatasetStore`` adapts it
to the ``DatasetStore`` port (ADR-0006), with a dataset card per save; ``import_dataset`` reads any
dataset on the Hub at a pinned commit.
"""

from evalr.hf.cards import DATA_FILE, dataset_card, read_card
from evalr.hf.imports import import_dataset
from evalr.hf.store import COMMIT, HfDatasetStore, HubApi, pinned, resolve_revision

__all__ = [
    "COMMIT",
    "DATA_FILE",
    "HfDatasetStore",
    "HubApi",
    "dataset_card",
    "import_dataset",
    "pinned",
    "read_card",
    "resolve_revision",
]
