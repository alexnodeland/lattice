import asyncio

from pydantic import BaseModel

from evalr.contracts import ContractInput, ContractVerdict
from evalr.contracts.support import contract_dataset
from evalr.core import Example, FunctionEvaluator
from evalr.memory import InMemoryExperimentTracker

from ..conftest import Spans, context_of


class Echo(BaseModel):
    title: str


def judge(output: Echo) -> ContractVerdict:
    return ContractVerdict(rating=3, resolved=True)


async def echo(example: Example[ContractInput, ContractVerdict]) -> Echo:
    return Echo(title=example.input.title)


async def test_each_example_runs_in_its_own_span(spans: Spans) -> None:
    tracker = InMemoryExperimentTracker(tracer_provider=spans.provider)
    result = await tracker.run_experiment(
        "exp",
        dataset=contract_dataset("d", count=3),
        task=echo,
        evaluators=[
            FunctionEvaluator(judge, verdict_type=ContractVerdict, tracer_provider=spans.provider)
        ],
        metadata={"model": "m1"},
    )
    items = [s for s in spans.finished() if s.name == "evalr.experiment.item exp"]
    assert len(items) == 3
    assert sorted(str(dict(s.attributes or {})["evalr.example.id"]) for s in items) == [
        "example-0",
        "example-1",
        "example-2",
    ]
    assert all(dict(s.attributes or {})["evalr.experiment.metadata.model"] == "m1" for s in items)
    traces = {f"{context_of(s).trace_id:032x}" for s in items}
    assert {item.trace_id for item in result.items} == traces
    assert result.verdicts("judge").keys() == {"example-0", "example-1", "example-2"}


async def test_runs_are_numbered_and_kept() -> None:
    tracker = InMemoryExperimentTracker()
    dataset = contract_dataset("d", count=1)
    first = await tracker.run_experiment("exp", dataset=dataset, task=echo, evaluators=[])
    second = await tracker.run_experiment("exp", dataset=dataset, task=echo, evaluators=[])
    other = await tracker.run_experiment("other", dataset=dataset, task=echo, evaluators=[])
    assert [first.run_name, second.run_name, other.run_name] == ["exp #1", "exp #2", "other #1"]
    assert tracker.runs == [first, second, other]
    assert first.url is None


async def test_concurrency_is_limited() -> None:
    running = 0
    peak = 0

    async def slow(example: Example[ContractInput, ContractVerdict]) -> Echo:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.001)
        running -= 1
        return Echo(title=example.id)

    await InMemoryExperimentTracker().run_experiment(
        "exp", dataset=contract_dataset("d", count=8), task=slow, evaluators=[], max_concurrency=3
    )
    assert peak == 3
