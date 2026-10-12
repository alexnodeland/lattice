"""Minimal type stubs for the parts of Hugging Face's datasets that evalr uses (it ships none)."""

from collections.abc import Iterator
from typing import Any

class Dataset:
    def __iter__(self) -> Iterator[dict[str, Any]]: ...
    def __len__(self) -> int: ...

def load_dataset(
    path: str,
    name: str | None = None,
    *,
    split: str,
    revision: str | None = None,
    cache_dir: str | None = None,
    token: str | bool | None = None,
) -> Dataset: ...
