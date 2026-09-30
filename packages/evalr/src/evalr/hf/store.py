"""The Hugging Face Hub as a ``DatasetStore``.

A dataset is a dataset repository of the same name (``org/helpfulness``). Each save is one
commit of two files: the examples as JSON Lines (``data/train.jsonl``) and a dataset card
(``README.md``) recording the source and version. A revision is the commit's hash, so loading
one reads the dataset exactly as it was saved, forever.
"""

import asyncio
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from huggingface_hub import CommitInfo, CommitOperationAdd, HfApi
from huggingface_hub.errors import (
    EntryNotFoundError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)
from huggingface_hub.hf_api import DatasetInfo
from pydantic import BaseModel, JsonValue

from evalr.core import Dataset, DatasetNotFound
from evalr.hf.cards import DATA_FILE, dataset_card, read_card

__all__ = ["COMMIT", "HfDatasetStore", "HubApi", "pinned", "resolve_revision"]

COMMIT = re.compile(r"[0-9a-f]{40}")
"""A full commit hash: the only revision that always names the same data."""

_REPOSITORY = "dataset"


class HubApi(Protocol):
    """The parts of ``huggingface_hub.HfApi`` the store uses."""

    def create_repo(
        self,
        repo_id: str,
        *,
        private: bool | None = None,
        repo_type: str | None = None,
        exist_ok: bool = False,
    ) -> object:
        """Create a repository, or do nothing if it exists and ``exist_ok``."""
        ...

    def create_commit(
        self,
        repo_id: str,
        operations: Iterable[CommitOperationAdd],
        *,
        commit_message: str,
        repo_type: str | None = None,
    ) -> CommitInfo:
        """Commit files to a repository."""
        ...

    def hf_hub_download(
        self,
        repo_id: str,
        filename: str,
        *,
        repo_type: str | None = None,
        revision: str | None = None,
    ) -> str:
        """Download a file of a repository at a revision, returning its local path."""
        ...

    def dataset_info(self, repo_id: str, *, revision: str | None = None) -> DatasetInfo:
        """Describe a dataset repository at a revision."""
        ...


def pinned(revision: str) -> bool:
    """Whether a revision is a full commit hash, which always names the same data."""
    return COMMIT.fullmatch(revision) is not None


class HfDatasetStore:
    """Saves datasets to the Hugging Face Hub, and loads them from it at a revision.

    The Hub's calls are synchronous, so they run in a worker thread.
    """

    def __init__(self, api: HubApi | None = None, *, private: bool = True) -> None:
        """Use the Hub.

        Args:
            api: The Hub's client; ``HfApi()`` by default, which finds a token as the Hugging
                Face tools do.
            private: Create new dataset repositories as private.
        """
        self.api: HubApi = api or HfApi()
        self.private = private

    async def save[InputT: BaseModel, VerdictT: BaseModel](
        self, dataset: Dataset[InputT, VerdictT], /
    ) -> str:
        """Commit the dataset's examples and card to the repository of its name.

        Returns:
            The commit's hash.
        """
        return await asyncio.to_thread(self._save, dataset)

    async def load[InputT: BaseModel, VerdictT: BaseModel](
        self,
        name: str,
        /,
        *,
        input_type: type[InputT],
        verdict_type: type[VerdictT],
        revision: str | None = None,
    ) -> Dataset[InputT, VerdictT]:
        """Read a dataset at a revision: a commit hash, a branch or a tag; the latest by default.

        Raises:
            DatasetNotFound: The Hub has no such repository, revision, or examples file.
            pydantic.ValidationError: The examples are not of these types.
        """
        try:
            description, records = await asyncio.to_thread(self._read, name, revision)
        except (RepositoryNotFoundError, RevisionNotFoundError, EntryNotFoundError) as error:
            raise DatasetNotFound(f"no dataset {name!r} at revision {revision!r}") from error
        return Dataset.from_records(
            name,
            records,
            input_type=input_type,
            verdict_type=verdict_type,
            description=description,
        )

    def _save[InputT: BaseModel, VerdictT: BaseModel](
        self, dataset: Dataset[InputT, VerdictT]
    ) -> str:
        lines = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in dataset.records()
        )
        self.api.create_repo(
            dataset.name, private=self.private, repo_type=_REPOSITORY, exist_ok=True
        )
        commit = self.api.create_commit(
            dataset.name,
            [
                CommitOperationAdd("README.md", dataset_card(dataset).encode()),
                CommitOperationAdd(DATA_FILE, lines.encode()),
            ],
            commit_message=f"evalr: {dataset.name} at {dataset.version}",
            repo_type=_REPOSITORY,
        )
        return commit.oid

    def _read(self, name: str, revision: str | None) -> tuple[str, list[dict[str, JsonValue]]]:
        data = self.api.hf_hub_download(name, DATA_FILE, repo_type=_REPOSITORY, revision=revision)
        card = self.api.hf_hub_download(name, "README.md", repo_type=_REPOSITORY, revision=revision)
        description = str(read_card(Path(card).read_text(encoding="utf-8")).get("description", ""))
        lines = Path(data).read_text(encoding="utf-8").splitlines()
        return description, [json.loads(line) for line in lines if line]


def resolve_revision(repo_id: str, revision: str = "main", *, api: HubApi | None = None) -> str:
    """Pin a branch or tag of a dataset repository to its commit hash.

    Raises:
        DatasetNotFound: The Hub has no such repository or revision.
        ValueError: The Hub reported no commit hash.
    """
    try:
        info = (api or HfApi()).dataset_info(repo_id, revision=revision)
    except (RepositoryNotFoundError, RevisionNotFoundError) as error:
        raise DatasetNotFound(f"no dataset {repo_id!r} at revision {revision!r}") from error
    if info.sha is None:
        raise ValueError(f"the Hub gave no commit for {repo_id!r} at {revision!r}")
    return info.sha
