"""Every dataset store adapter meets the DatasetStore contract."""

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from evalr.contracts import ContractInput, ContractVerdict, ContractViolation, check_dataset_store
from evalr.core import Dataset, DatasetStore
from evalr.jsonl import JsonlDatasetStore
from evalr.memory import InMemoryDatasetStore

STORES: dict[str, Callable[[Path], DatasetStore]] = {
    "memory": lambda tmp: InMemoryDatasetStore(),
    "jsonl": lambda tmp: JsonlDatasetStore(tmp / "datasets"),
}


@pytest.fixture(params=sorted(STORES))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> DatasetStore:
    return STORES[request.param](tmp_path)


async def test_the_store_meets_the_contract(store: DatasetStore) -> None:
    await check_dataset_store(store)


async def test_the_contract_accepts_any_unused_name(store: DatasetStore) -> None:
    await check_dataset_store(store, name="team/helpfulness")


class Forgetful:
    """Loads an empty dataset for any name: it never raises DatasetNotFound."""

    async def save[I: BaseModel, V: BaseModel](self, dataset: Dataset[I, V], /) -> str:
        return "r"

    async def load[I: BaseModel, V: BaseModel](
        self,
        name: str,
        /,
        *,
        input_type: type[I],
        verdict_type: type[V],
        revision: str | None = None,
    ) -> Dataset[I, V]:
        return Dataset(name, [], input_type=input_type, verdict_type=verdict_type)


class Silent(InMemoryDatasetStore):
    """Saves, but returns no revision."""

    async def save[I: BaseModel, V: BaseModel](self, dataset: Dataset[I, V], /) -> str:
        await super().save(dataset)
        return ""


class Undescribed(InMemoryDatasetStore):
    """Forgets descriptions."""

    async def load[I: BaseModel, V: BaseModel](
        self,
        name: str,
        /,
        *,
        input_type: type[I],
        verdict_type: type[V],
        revision: str | None = None,
    ) -> Dataset[I, V]:
        loaded = await super().load(
            name, input_type=input_type, verdict_type=verdict_type, revision=revision
        )
        return Dataset(name, loaded, input_type=input_type, verdict_type=verdict_type)


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (Forgetful(), "never saved must raise DatasetNotFound"),
        (Silent(), "save must return a revision"),
        (Undescribed(), "the description must be kept"),
    ],
    ids=["forgetful", "silent", "undescribed"],
)
async def test_a_broken_store_fails_the_contract(broken: DatasetStore, message: str) -> None:
    with pytest.raises(ContractViolation, match=message):
        await check_dataset_store(broken)


def test_the_contract_types_are_exported() -> None:
    assert ContractVerdict.model_fields["rating"].description == "How good it is"
    assert ContractInput(title="t", messages=[]).title == "t"
