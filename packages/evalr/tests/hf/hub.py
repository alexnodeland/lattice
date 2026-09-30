"""A fake of the Hugging Face Hub, in memory: repositories of commits, and downloads to a folder."""

import hashlib
from collections.abc import Iterable
from pathlib import Path

import httpx
from huggingface_hub import CommitInfo, CommitOperationAdd
from huggingface_hub.errors import (
    EntryNotFoundError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)
from huggingface_hub.hf_api import DatasetInfo


def _not_found(message: str) -> httpx.Response:
    return httpx.Response(404, request=httpx.Request("GET", "https://huggingface.co"), text=message)


class FakeHub:
    def __init__(self, downloads: Path) -> None:
        self.downloads = downloads
        self.repos: dict[str, list[tuple[str, dict[str, bytes]]]] = {}
        self.private: dict[str, bool] = {}
        self.tags: dict[str, dict[str, str]] = {}

    def create_repo(
        self,
        repo_id: str,
        *,
        private: bool | None = None,
        repo_type: str | None = None,
        exist_ok: bool = False,
    ) -> object:
        assert repo_type == "dataset"
        if repo_id in self.repos:
            assert exist_ok
        else:
            self.repos[repo_id] = []
            self.private[repo_id] = bool(private)
        return f"https://huggingface.co/datasets/{repo_id}"

    def create_commit(
        self,
        repo_id: str,
        operations: Iterable[CommitOperationAdd],
        *,
        commit_message: str,
        repo_type: str | None = None,
    ) -> CommitInfo:
        commits = self.repos[repo_id]
        files = dict(commits[-1][1]) if commits else {}
        for operation in operations:
            content = operation.path_or_fileobj
            assert isinstance(content, bytes)
            files[operation.path_in_repo] = content
        sha = hashlib.sha1(
            f"{len(commits)}{commit_message}".encode() + b"".join(files.values())
        ).hexdigest()
        commits.append((sha, files))
        return CommitInfo(
            commit_url=f"https://huggingface.co/datasets/{repo_id}/commit/{sha}",
            commit_message=commit_message,
            commit_description="",
            oid=sha,
        )

    def _commit(self, repo_id: str, revision: str | None) -> tuple[str, dict[str, bytes]]:
        if repo_id not in self.repos:
            raise RepositoryNotFoundError(f"{repo_id} not found", response=_not_found("repo"))
        commits = self.repos[repo_id]
        wanted = self.tags.get(repo_id, {}).get(revision or "main", revision)
        if wanted in (None, "main") and commits:
            return commits[-1]
        for sha, files in commits:
            if sha == wanted:
                return sha, files
        raise RevisionNotFoundError(f"{revision} not found", response=_not_found("revision"))

    def hf_hub_download(
        self,
        repo_id: str,
        filename: str,
        *,
        repo_type: str | None = None,
        revision: str | None = None,
    ) -> str:
        sha, files = self._commit(repo_id, revision)
        if filename not in files:
            raise EntryNotFoundError(f"{filename} not in {repo_id}")
        path = self.downloads / repo_id / sha / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(files[filename])
        return str(path)

    def dataset_info(self, repo_id: str, *, revision: str | None = None) -> DatasetInfo:
        sha, _ = self._commit(repo_id, revision)
        return DatasetInfo(id=repo_id, sha=sha)
