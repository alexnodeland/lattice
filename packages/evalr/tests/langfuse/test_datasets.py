from collections.abc import Iterator

import pytest
from langfuse import Langfuse

from evalr.contracts import ContractInput, ContractVerdict, check_dataset_store
from evalr.contracts.support import contract_dataset
from evalr.core import Dataset, DatasetNotFound
from evalr.langfuse import LangfuseDatasetStore, item_id

from .server import FakeLangfuse, connected


@pytest.fixture
def server() -> FakeLangfuse:
    return FakeLangfuse()


@pytest.fixture
def client(server: FakeLangfuse) -> Iterator[Langfuse]:
    with connected(server) as (client, _):
        yield client


async def test_the_store_meets_the_contract(client: Langfuse) -> None:
    await check_dataset_store(LangfuseDatasetStore(client))


async def test_items_are_keyed_by_dataset_and_example(
    client: Langfuse, server: FakeLangfuse
) -> None:
    store = LangfuseDatasetStore(client)
    dataset = contract_dataset("team/helpfulness", count=2)
    await store.save(dataset)
    assert set(server.history) == {item_id("team/helpfulness", e.id) for e in dataset}
    item = server.item(item_id("team/helpfulness", "example-1"))
    assert item["expectedOutput"]["verdict"]["rating"] == 2
    assert item["metadata"] == {
        "source": "contract",
        "index": 1,
        "weight": 1.0,
        "evalr": {"example_id": "example-1"},
    }
    assert item["sourceTraceId"] == f"{1:032x}"
    assert server.datasets["team/helpfulness"]["metadata"] == {
        "evalr": {"input_type": "ContractInput", "verdict_type": "ContractVerdict"}
    }


async def test_saving_unchanged_examples_writes_nothing(
    client: Langfuse, server: FakeLangfuse
) -> None:
    store = LangfuseDatasetStore(client)
    dataset = contract_dataset("d", count=3)
    first = await store.save(dataset)
    writes = len(server.writes)
    assert await store.save(dataset) == first
    assert len(server.writes) == writes


async def test_items_made_in_langfuse_load_with_their_expected_output_as_the_verdict(
    client: Langfuse,
) -> None:
    client.create_dataset(name="labelled")
    client.create_dataset_item(
        dataset_name="labelled",
        id="by-hand",
        input={"title": "t", "messages": ["m"]},
        expected_output={"rating": 3, "resolved": True},
        metadata={"who": "annotator"},
    )
    loaded = await LangfuseDatasetStore(client).load(
        "labelled", input_type=ContractInput, verdict_type=ContractVerdict
    )
    (example,) = loaded
    assert example.id == "by-hand"
    assert example.verdict == ContractVerdict(rating=3, resolved=True)
    assert example.metadata == {"who": "annotator"}
    assert loaded.description == ""


async def test_unknown_datasets_are_not_found(client: Langfuse) -> None:
    with pytest.raises(DatasetNotFound):
        await LangfuseDatasetStore(client).load(
            "missing", input_type=ContractInput, verdict_type=ContractVerdict
        )


async def load_ids(store: LangfuseDatasetStore, revision: str | None = None) -> set[str]:
    loaded = await store.load(
        "d", input_type=ContractInput, verdict_type=ContractVerdict, revision=revision
    )
    return {e.id for e in loaded}


@pytest.mark.parametrize("removed", ["example-0", "example-2"])
async def test_removed_examples_stay_archived(
    client: Langfuse, server: FakeLangfuse, removed: str
) -> None:
    store = LangfuseDatasetStore(client)
    full = contract_dataset("d", count=3)
    fewer = full.filter(lambda e: e.id != removed)
    await store.save(full)
    revision = await store.save(fewer)
    assert server.item(item_id("d", removed))["status"] == "ARCHIVED"
    assert await store.save(fewer) == revision
    assert await load_ids(store) == await load_ids(store, revision) == {e.id for e in fewer}


async def test_an_item_deleted_in_langfuse_stays_deleted(client: Langfuse) -> None:
    store = LangfuseDatasetStore(client)
    full = contract_dataset("d", count=3)
    await store.save(full)
    client.api.dataset_items.delete(id=item_id("d", "example-0"))
    revision = await store.save(full.filter(lambda e: e.id != "example-0"))
    assert await load_ids(store, revision) == {"example-1", "example-2"}


async def test_an_example_that_loses_its_trace_loses_it_in_langfuse(
    client: Langfuse, server: FakeLangfuse
) -> None:
    store = LangfuseDatasetStore(client)
    traced = contract_dataset("d", count=2)
    first = await store.save(traced)
    untraced = Dataset(
        "d",
        [traced["example-0"], traced["example-1"].model_copy(update={"trace_id": None})],
        input_type=ContractInput,
        verdict_type=ContractVerdict,
        description=traced.description,
    )
    second = await store.save(untraced)
    writes = len(server.writes)
    assert await store.save(untraced) == second
    assert len(server.writes) == writes
    loaded = await store.load("d", input_type=ContractInput, verdict_type=ContractVerdict)
    assert loaded["example-1"].trace_id is None
    assert loaded.version == untraced.version
    pinned = await store.load(
        "d", input_type=ContractInput, verdict_type=ContractVerdict, revision=first
    )
    assert pinned["example-1"].trace_id == traced["example-1"].trace_id
