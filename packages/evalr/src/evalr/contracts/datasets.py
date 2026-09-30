"""The ``DatasetStore`` contract."""

from pydantic import BaseModel, ValidationError

from evalr.contracts.support import (
    ContractInput,
    ContractVerdict,
    contract_dataset,
    contract_example,
    expect_raises,
    require,
)
from evalr.core import Dataset, DatasetNotFound, DatasetStore

__all__ = ["check_dataset_store"]


class _Stricter(BaseModel):
    """A verdict type the contract's examples do not satisfy."""

    missing: int


async def check_dataset_store(store: DatasetStore, *, name: str = "evalr-contract") -> None:
    """Check that a dataset store keeps every revision it saves, and nothing else.

    The store must not hold a dataset named ``name`` yet.

    Raises:
        ContractViolation: The store behaves differently from the ``DatasetStore`` contract.
    """
    await expect_raises(
        DatasetNotFound,
        store.load(name, input_type=ContractInput, verdict_type=ContractVerdict),
        "loading a dataset that was never saved must raise DatasetNotFound",
    )

    first = contract_dataset(name)
    revision = await store.save(first)
    require(bool(revision), "save must return a revision")
    _require_same(await _load(store, name), first, "the latest revision after a save")

    await store.save(first)
    _require_same(await _load(store, name), first, "the latest revision after saving it again")

    examples = list(first)
    changed = Dataset(
        name,
        [*examples[1:-1], examples[-1].model_copy(update={"verdict": None}), contract_example(99)],
        input_type=ContractInput,
        verdict_type=ContractVerdict,
        description="Changed by the evalr contract suite",
    )
    second = await store.save(changed)
    require(second != revision, "saving different examples must make a new revision")
    _require_same(await _load(store, name), changed, "the latest revision after a change")
    _require_same(await _load(store, name, revision), first, "an earlier revision", check=False)

    await expect_raises(
        DatasetNotFound,
        store.load(
            name,
            input_type=ContractInput,
            verdict_type=ContractVerdict,
            revision="evalr-contract-missing-revision",
        ),
        "loading a revision that was never saved must raise DatasetNotFound",
    )
    await expect_raises(
        ValidationError,
        store.load(name, input_type=ContractInput, verdict_type=_Stricter),
        "loading examples as a type they do not satisfy must raise a ValidationError",
    )


async def _load(
    store: DatasetStore, name: str, revision: str | None = None
) -> Dataset[ContractInput, ContractVerdict]:
    return await store.load(
        name, input_type=ContractInput, verdict_type=ContractVerdict, revision=revision
    )


def _require_same(
    loaded: Dataset[ContractInput, ContractVerdict],
    saved: Dataset[ContractInput, ContractVerdict],
    what: str,
    *,
    check: bool = True,
) -> None:
    require(loaded.name == saved.name, f"{what}: the name must be kept")
    require(
        loaded.version == saved.version and {e.id for e in loaded} == {e.id for e in saved},
        f"{what}: the examples must be exactly those saved",
    )
    if check:
        require(loaded.description == saved.description, f"{what}: the description must be kept")
