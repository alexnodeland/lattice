"""Importing any dataset on the Hugging Face Hub, at a pinned commit."""

import asyncio
from collections.abc import Callable
from typing import Any

import datasets
from pydantic import BaseModel

from evalr.core import Dataset, Example
from evalr.hf.store import pinned

__all__ = ["import_dataset"]


async def import_dataset[InputT: BaseModel, VerdictT: BaseModel](
    path: str,
    *,
    revision: str,
    input_type: type[InputT],
    verdict_type: type[VerdictT],
    to_example: Callable[[dict[str, Any]], Example[InputT, VerdictT]] | None = None,
    name: str | None = None,
    description: str = "",
    split: str = "train",
    cache_dir: str | None = None,
    token: str | bool | None = None,
) -> Dataset[InputT, VerdictT]:
    """Load a dataset from the Hub (or a local directory) with ``datasets``, as examples.

    Only a full commit hash names the same data every time, so nothing else is accepted: pin
    a branch or tag first with ``resolve_revision``.

    Args:
        path: The dataset's repository (``org/name``), or a local directory of data files.
        revision: The commit to load.
        input_type: The Pydantic model of the examples' inputs.
        verdict_type: The Pydantic model of the examples' verdicts.
        to_example: Turns a row into an example; rows are read as evalr's records by default.
        name: The dataset's name; the path by default.
        description: What the dataset holds.
        split: The split to load.
        cache_dir: Where ``datasets`` caches; its default by default.
        token: A Hugging Face token, for private datasets.

    Raises:
        ValueError: The revision is not a full commit hash.
    """
    if not pinned(revision):
        raise ValueError(
            f"import {path!r} at a full commit hash, not {revision!r}; "
            "resolve_revision pins a branch or tag"
        )
    rows = await asyncio.to_thread(
        datasets.load_dataset,
        path,
        split=split,
        revision=revision,
        cache_dir=cache_dir,
        token=token,
    )
    convert = to_example or Example[input_type, verdict_type].model_validate
    return Dataset(
        name or path,
        [convert(row) for row in rows],
        input_type=input_type,
        verdict_type=verdict_type,
        description=description,
    )
