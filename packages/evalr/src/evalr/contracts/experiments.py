"""The ``ExperimentTracker`` contract."""

from pydantic import BaseModel

from evalr.contracts.support import (
    ContractInput,
    ContractVerdict,
    contract_dataset,
    require,
)
from evalr.core import Example, ExperimentTracker, FunctionEvaluator, ItemResult

__all__ = ["ContractOutput", "check_experiment_tracker"]

_FAILING_TASK = "example-3"
_REFUSED = "Thread 1"


class ContractOutput(BaseModel):
    """What the contract experiment's task produces."""

    title: str
    reply: str


async def _task(example: Example[ContractInput, ContractVerdict]) -> ContractOutput:
    if example.id == _FAILING_TASK:
        raise RuntimeError("the task failed on purpose")
    return ContractOutput(title=example.input.title, reply=example.input.messages[-1])


def _length(output: ContractOutput) -> ContractVerdict:
    return ContractVerdict(rating=min(5, len(output.reply) // 3), resolved=True)


def _picky(output: ContractOutput) -> ContractVerdict:
    if output.title == _REFUSED:
        raise ValueError("picky refused on purpose")
    return ContractVerdict(rating=3, resolved=False)


async def check_experiment_tracker(tracker: ExperimentTracker) -> None:
    """Check that a tracker runs every example, judges every output, and isolates failures.

    Raises:
        ContractViolation: The tracker behaves differently from the ``ExperimentTracker``
            contract.
    """
    dataset = contract_dataset("evalr-contract-experiment", count=5)
    evaluators = [
        FunctionEvaluator(_length, verdict_type=ContractVerdict, name="length"),
        FunctionEvaluator(_picky, verdict_type=ContractVerdict, name="picky"),
    ]
    result = await tracker.run_experiment(
        "evalr-contract",
        dataset=dataset,
        task=_task,
        evaluators=evaluators,
        run_name="evalr contract run",
        max_concurrency=2,
        metadata={"purpose": "contract"},
    )
    require(
        (result.name, result.run_name) == ("evalr-contract", "evalr contract run"),
        "the experiment and run names must be kept",
    )
    require(
        (result.dataset, result.dataset_version) == (dataset.name, dataset.version),
        "the result must name the dataset and its version",
    )
    require(
        [item.example_id for item in result.items] == [example.id for example in dataset],
        "there must be one item per example, in the dataset's order",
    )
    for example, item in zip(dataset, result.items, strict=True):
        if example.id == _FAILING_TASK:
            require(
                item.output is None
                and not item.verdicts
                and any("the task failed on purpose" in error for error in item.errors),
                f"{item.example_id}: a failed task must leave no output and record its error",
            )
            continue
        output = await _task(example)
        require(item.output == output, f"{item.example_id}: the task's output must be kept")
        _require_verdicts(item, output)


def _require_verdicts(item: ItemResult[ContractOutput], output: ContractOutput) -> None:
    expected = [("length", _length(output))]
    if output.title == _REFUSED:
        require(
            any("picky" in error and "refused on purpose" in error for error in item.errors),
            f"{item.example_id}: a failed evaluator must record its error",
        )
    else:
        expected.append(("picky", _picky(output)))
        require(not item.errors, f"{item.example_id}: nothing failed, so no errors")
    require(
        [(v.evaluator, v.value) for v in item.verdicts] == expected,
        f"{item.example_id}: every evaluator that succeeded must give its verdict, in order",
    )
    require(
        item.trace_id is None or all(v.trace_id == item.trace_id for v in item.verdicts),
        f"{item.example_id}: verdicts must record the item's trace",
    )
