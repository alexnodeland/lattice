"""A dataset store on local JSON Lines files.

Each dataset is a directory under the store's root, named by the dataset (``org/helpfulness``
becomes ``org/helpfulness/``). Every revision is a file of JSON records, one example to a line,
named by the dataset's content hash, so saving the same examples again rewrites nothing.
``dataset.json`` names the latest revision and holds the description::

    root/
      helpfulness/
        dataset.json            {"description": "...", "latest": "3f2a9c0d1e4b5a67"}
        3f2a9c0d1e4b5a67.jsonl  one example per line
"""

import asyncio
import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, JsonValue

from evalr.core import Dataset, DatasetNotFound

__all__ = ["JsonlDatasetStore"]

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*")
_REVISION = re.compile(r"[0-9a-f]{16}")


class JsonlDatasetStore:
    """Saves datasets as JSON Lines files under a root directory.

    The files are plain JSON Lines, readable by any tool, including Hugging Face's
    ``load_dataset("json", data_files=...)``.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        """Use a directory, created on the first save.

        Args:
            root: The directory holding the datasets.
        """
        self.root = Path(root)

    def _directory(self, name: str) -> Path:
        if not _NAME.fullmatch(name):
            raise ValueError(
                f"invalid dataset name {name!r}: use segments of letters, digits, '.', '_' and "
                "'-', each starting with a letter or digit, separated by '/'"
            )
        return self.root / name

    async def save[InputT: BaseModel, VerdictT: BaseModel](
        self, dataset: Dataset[InputT, VerdictT], /
    ) -> str:
        """Write the dataset's revision and make it the latest.

        Returns:
            The dataset's content hash, which names the revision.

        Raises:
            ValueError: The dataset's name cannot be a path under the root.
        """
        directory = self._directory(dataset.name)
        revision = dataset.version
        lines = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in dataset.records()
        )
        index = {"description": dataset.description, "latest": revision}
        await asyncio.to_thread(_write, directory, revision, lines, index)
        return revision

    async def load[InputT: BaseModel, VerdictT: BaseModel](
        self,
        name: str,
        /,
        *,
        input_type: type[InputT],
        verdict_type: type[VerdictT],
        revision: str | None = None,
    ) -> Dataset[InputT, VerdictT]:
        """Read the latest revision of a dataset, or the one given.

        Raises:
            DatasetNotFound: No dataset has the name, or it has no such revision.
            ValueError: The name cannot be a path under the root.
        """
        directory = self._directory(name)
        if revision is not None and not _REVISION.fullmatch(revision):
            raise DatasetNotFound(f"dataset {name!r} has no revision {revision!r}")
        found = await asyncio.to_thread(_read, directory, revision)
        if found is None:
            raise DatasetNotFound(f"no dataset named {name!r} with revision {revision!r}")
        description, records = found
        return Dataset.from_records(
            name,
            records,
            input_type=input_type,
            verdict_type=verdict_type,
            description=description,
        )


def _write(directory: Path, revision: str, lines: str, index: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    data = directory / f"{revision}.jsonl"
    if not data.exists():
        _replace(data, lines)
    _replace(directory / "dataset.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n")


def _replace(path: Path, text: str) -> None:
    """Write a file whole, so a reader never sees half of it."""
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def _read(directory: Path, revision: str | None) -> tuple[str, list[dict[str, JsonValue]]] | None:
    index_path = directory / "dataset.json"
    if not index_path.is_file():
        return None
    index = json.loads(index_path.read_text(encoding="utf-8"))
    data = directory / f"{revision or index['latest']}.jsonl"
    if not data.is_file():
        return None
    lines = data.read_text(encoding="utf-8").splitlines()
    return index["description"], [json.loads(line) for line in lines if line]
