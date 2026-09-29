from collections.abc import Iterator

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evalr.contracts import ContractInput, ContractVerdict, check_experiment_tracker
from evalr.contracts.support import contract_dataset
from evalr.core import Example, FunctionEvaluator, Verdict
from evalr.langfuse import LangfuseExperimentTracker, evaluations

from ..conftest import Spans, context_of
from ..decision.models import Helpfulness
from .server import FakeLangfuse, connected


@pytest.fixture
def server() -> FakeLangfuse:
    return FakeLangfuse()


@pytest.fixture
def langfuse(server: FakeLangfuse) -> Iterator[tuple[Langfuse, InMemorySpanExporter]]:
    with connected(server) as pair:
        yield pair


async def test_the_tracker_meets_the_contract(
    langfuse: tuple[Langfuse, InMemorySpanExporter],
) -> None:
    client, _ = langfuse
    await check_experiment_tracker(LangfuseExperimentTracker(client))


class Reply(ContractInput):
    reply: str


async def test_items_run_in_their_own_traces_and_verdicts_become_scores(
    langfuse: tuple[Langfuse, InMemorySpanExporter], server: FakeLangfuse, spans: Spans
) -> None:
    client, exporter = langfuse
    dataset = contract_dataset("d", count=2)

    async def answer(example: Example[ContractInput, ContractVerdict]) -> Reply:
        return Reply(title=example.input.title, messages=example.input.messages, reply="done")

    def judge(reply: Reply) -> ContractVerdict:
        return ContractVerdict(rating=4, resolved=True, reason="it said done")

    result = await LangfuseExperimentTracker(client).run_experiment(
        "prompt-v2",
        dataset=dataset,
        task=answer,
        evaluators=[
            FunctionEvaluator(
                judge, verdict_type=ContractVerdict, name="judge", tracer_provider=spans.provider
            )
        ],
        metadata={"prompt": "v2"},
    )
    assert result.run_name.startswith("prompt-v2 - ")
    assert result.url is None
    traces = {item.trace_id for item in result.items}
    assert len(traces) == 2
    evaluate = [s for s in spans.finished() if s.name == "evalr.evaluate judge"]
    assert {f"{context_of(s).trace_id:032x}" for s in evaluate} == traces
    langfuse_spans = {s.context.span_id: s.name for s in exporter.get_finished_spans() if s.context}
    assert {langfuse_spans[s.parent.span_id] for s in evaluate if s.parent} == {"judge"}
    assert {"experiment-item-run", "experiment-item-task"} <= set(langfuse_spans.values())
    comments = {body["name"]: body.get("comment") for body in server.scores.values()}
    assert comments["contract_verdict.rating"] == "reason: it said done"
    assert "contract_verdict.reason" not in comments


def test_evaluations_leave_text_to_comments() -> None:
    verdict = Verdict(
        value=Helpfulness(rating=4, resolved=True), evaluator="e", version="1", trace_id="f" * 32
    )
    result = evaluations(verdict)
    assert [(e.name, e.value, e.data_type, e.comment) for e in result] == [
        ("helpfulness.rating", 4.0, "NUMERIC", None),
        ("helpfulness.resolved", True, "BOOLEAN", None),
        ("helpfulness.category", "other", "CATEGORICAL", None),
        ("helpfulness.share", 0.5, "NUMERIC", None),
    ]
