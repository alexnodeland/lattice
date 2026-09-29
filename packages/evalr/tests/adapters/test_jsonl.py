import json
from pathlib import Path

import pytest

from evalr.contracts import ContractInput, ContractVerdict
from evalr.contracts.support import contract_dataset
from evalr.core import DatasetNotFound
from evalr.jsonl import JsonlDatasetStore


async def test_revisions_are_plain_json_lines_named_by_content(tmp_path: Path) -> None:
    store = JsonlDatasetStore(tmp_path)
    dataset = contract_dataset("team/helpfulness", count=3)
    revision = await store.save(dataset)
    directory = tmp_path / "team" / "helpfulness"
    assert {p.name for p in directory.iterdir()} == {"dataset.json", f"{revision}.jsonl"}
    assert json.loads((directory / "dataset.json").read_text()) == {
        "description": dataset.description,
        "latest": revision,
    }
    lines = (directory / f"{revision}.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == dataset.records()


async def test_another_store_on_the_same_root_reads_what_was_saved(tmp_path: Path) -> None:
    dataset = contract_dataset("d")
    revision = await JsonlDatasetStore(tmp_path).save(dataset)
    loaded = await JsonlDatasetStore(tmp_path).load(
        "d", input_type=ContractInput, verdict_type=ContractVerdict, revision=revision
    )
    assert list(loaded) == list(dataset)


@pytest.mark.parametrize("name", ["", "/abs", "../up", "a/../b", "a//b", ".hidden", "a/", "a b"])
async def test_names_must_be_paths_under_the_root(tmp_path: Path, name: str) -> None:
    store = JsonlDatasetStore(tmp_path)
    with pytest.raises(ValueError, match="invalid dataset name"):
        await store.load(name, input_type=ContractInput, verdict_type=ContractVerdict)
    with pytest.raises(ValueError, match="invalid dataset name"):
        await store.save(contract_dataset(name))


async def test_an_unsaved_revision_is_not_found(tmp_path: Path) -> None:
    store = JsonlDatasetStore(tmp_path)
    await store.save(contract_dataset("d"))
    with pytest.raises(DatasetNotFound):
        await store.load(
            "d", input_type=ContractInput, verdict_type=ContractVerdict, revision="0" * 16
        )
