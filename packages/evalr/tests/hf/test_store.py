import json
from pathlib import Path

import pytest
from huggingface_hub import HfApi
from huggingface_hub.hf_api import DatasetInfo

from evalr.contracts import ContractInput, ContractVerdict, check_dataset_store
from evalr.contracts.support import contract_dataset
from evalr.core import DatasetNotFound
from evalr.hf import DATA_FILE, HfDatasetStore, HubApi, pinned, read_card, resolve_revision

from .hub import FakeHub


@pytest.fixture
def hub(tmp_path: Path) -> FakeHub:
    return FakeHub(tmp_path / "downloads")


async def test_the_store_meets_the_contract(hub: FakeHub) -> None:
    await check_dataset_store(HfDatasetStore(hub), name="org/evalr-contract")


async def test_each_save_is_one_commit_of_the_examples_and_a_card(hub: FakeHub) -> None:
    dataset = contract_dataset("org/helpfulness", count=3)
    revision = await HfDatasetStore(hub, private=False).save(dataset)
    assert pinned(revision)
    ((sha, files),) = hub.repos["org/helpfulness"]
    assert sha == revision
    assert hub.private["org/helpfulness"] is False
    assert set(files) == {"README.md", DATA_FILE}
    lines = files[DATA_FILE].decode().splitlines()
    assert [json.loads(line) for line in lines] == dataset.records()
    card = files["README.md"].decode()
    assert read_card(card) == {
        "format": 1,
        "input_type": "ContractInput",
        "verdict_type": "ContractVerdict",
        "version": dataset.version,
        "description": dataset.description,
    }
    assert "Made with [evalr](https://lattice.alexnodeland.com/evalr/)" in card
    assert "| Examples | 3, 3 with a verdict |" in card
    assert "| `rating` | ordinal | How good it is |" in card
    assert '"path": "data/train.jsonl"' in card


async def test_a_repository_without_examples_is_not_found(hub: FakeHub) -> None:
    hub.create_repo("org/empty", repo_type="dataset")
    hub.repos["org/empty"].append(("e" * 40, {"README.md": b"# empty"}))
    with pytest.raises(DatasetNotFound):
        await HfDatasetStore(hub).load(
            "org/empty", input_type=ContractInput, verdict_type=ContractVerdict
        )


async def test_a_card_evalr_did_not_write_gives_no_description(hub: FakeHub) -> None:
    store = HfDatasetStore(hub)
    await store.save(contract_dataset("org/d", count=1))
    sha, files = hub.repos["org/d"][-1]
    hub.repos["org/d"].append((sha[::-1], {**files, "README.md": b"---\nlicense: mit\n---\n# d"}))
    loaded = await store.load("org/d", input_type=ContractInput, verdict_type=ContractVerdict)
    assert loaded.description == ""
    assert read_card("# no metadata") == {}


async def test_branches_and_tags_resolve_to_commits(hub: FakeHub) -> None:
    revision = await HfDatasetStore(hub).save(contract_dataset("org/d", count=1))
    hub.tags["org/d"] = {"v1": revision}
    assert resolve_revision("org/d", "v1", api=hub) == revision
    assert resolve_revision("org/d", api=hub) == revision
    with pytest.raises(DatasetNotFound):
        resolve_revision("org/missing", api=hub)


def test_a_revision_without_a_commit_is_refused() -> None:
    class Headless(FakeHub):
        def dataset_info(self, repo_id: str, *, revision: str | None = None) -> DatasetInfo:
            return DatasetInfo(id=repo_id, sha=None)

    with pytest.raises(ValueError, match="no commit"):
        resolve_revision("org/d", api=Headless(Path(".")))


def test_only_full_commit_hashes_are_pinned() -> None:
    assert pinned("0" * 40)
    assert not pinned("main")
    assert not pinned("abc1234")
    assert not pinned("A" * 40)


def test_the_default_client_is_the_hubs() -> None:
    assert isinstance(HfDatasetStore().api, HfApi)
    api: HubApi = HfApi()
    assert api is not None
