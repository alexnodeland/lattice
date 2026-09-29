import pytest

from evalr import collect
from evalr.contracts import ContractInput, ContractVerdict
from evalr.contracts.support import contract_example
from evalr.core import DuplicateExample
from evalr.memory import InMemoryFeedbackSource


async def test_collect_gathers_a_source_into_a_dataset() -> None:
    examples = [contract_example(i) for i in range(4)]
    source = InMemoryFeedbackSource(
        examples, input_type=ContractInput, verdict_type=ContractVerdict
    )
    dataset = await collect("helpfulness", source, description="From feedback")
    assert list(dataset) == examples
    assert (dataset.name, dataset.description) == ("helpfulness", "From feedback")
    assert (dataset.input_type, dataset.verdict_type) == (ContractInput, ContractVerdict)


async def test_a_source_with_duplicate_ids_is_rejected() -> None:
    source = InMemoryFeedbackSource(
        [contract_example(1), contract_example(1)],
        input_type=ContractInput,
        verdict_type=ContractVerdict,
    )
    with pytest.raises(DuplicateExample):
        await collect("d", source)
