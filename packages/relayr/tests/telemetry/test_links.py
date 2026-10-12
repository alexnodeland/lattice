"""Phase 4's exit criterion: traces linked across the bridge, and sessions tagged with each other.

In Tempo, a turn started by a run links to the run's span. In Langfuse, each session carries the
other's tag.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from langfuse import propagate_attributes
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent

import artifactr
import artifactr.agent
import artifactr.core as a
import reflexr
import reflexr.workspace as r
from relayr.events import ArtifactCreated
from relayr.langfuse import bridged_run, bridged_turns
from relayr.ledger import Ledger
from relayr.outbound import Allowlist, Outbound
from tests.app_types import Note
from tests.outbound.test_actions import reply
from tests.stack import ALICE, KEY, Stack, bridged, until

ACT = reflexr.Rule(
    name="app:act",
    when=reflexr.on(ArtifactCreated).where(reflexr.F.author.kind.eq("user")),
    then=reflexr.run("act"),
)


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def provider(exporter: InMemorySpanExporter) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


@pytest.fixture
async def runner(
    ledger: Ledger, provider: TracerProvider
) -> AsyncIterator[artifactr.agent.Runner[None]]:
    agent = Agent(
        artifactr.agent.function_model(reply),
        deps_type=artifactr.agent.Session[None],
        capabilities=[artifactr.agent.ArtifactWorkspace(types=[Note])],
    )
    started = artifactr.agent.Runner(
        agent, app=None, tracer_provider=provider, turn_context=bridged_turns(ledger)
    )
    yield started
    await started.aclose()


def named(spans: Sequence[ReadableSpan], name: str) -> ReadableSpan:
    [span] = [s for s in spans if s.name == name]
    return span


async def finished(exporter: InMemorySpanExporter, *names: str) -> list[ReadableSpan]:
    """Each named span, once every one of them has ended: a bounded poll.

    A span ends after what it committed is bridged, so the log alone doesn't say it has.
    """
    spans: Sequence[ReadableSpan] = ()

    async def ended() -> bool:
        nonlocal spans
        spans = exporter.get_finished_spans()
        return all(any(s.name == name for s in spans) for name in names)

    await until(ended)
    return [named(spans, name) for name in names]


async def act(reaction: r.Reaction[Outbound]) -> None:
    await reaction.deps.acting(reaction).send("please look")


async def test_traces_link_across_the_bridge(
    ledger: Ledger,
    stack: Stack,
    exporter: InMemorySpanExporter,
    provider: TracerProvider,
    runner: artifactr.agent.Runner[None],
) -> None:
    app = stack.process(
        ledger,
        rules=[ACT],
        actions={"act": act},
        allowlists={"app:act": Allowlist(turns=True)},
        runner=runner,
        tracer_provider=provider,
        run_context=bridged_run,
    )
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    await alice.create(Note(text=""), thread_id=thread.id)
    await bridged(stack, 1)
    await app.reactor.settle()

    created, bridge, publish, run, turn = await finished(
        exporter,
        "artifactr.commit create_artifact",
        "relayr.bridge artifact_created",
        "reflexr.publish artifactr:artifact_created",
        "invoke_workflow app:act",
        "invoke_workflow turn",
    )

    # Tempo: each side's trace links to the other's.
    assert linked(turn) == [ids(run)], "the turn links to the run"
    assert linked(bridge) == [ids(created)], "the bridged event, to what committed it"
    assert publish.parent is not None
    assert publish.parent.span_id == ids(bridge)[1]
    assert linked(run) == [ids(publish)], "and the run, to its event"

    # Langfuse: each session carries the other's tag.
    chain = attribute(run, "session.id")
    assert attribute(run, "user.id") == "alice", "the person who acted in artifactr"
    assert f"thread:{thread.id}" in tags(run)
    assert attribute(turn, "session.id") == thread.id
    assert tags(turn) == ("tenant:acme", "workspace:prod", "rule:app:act", f"chain:{chain}")


def ids(span: ReadableSpan) -> tuple[int, int]:
    assert span.context is not None
    return span.context.trace_id, span.context.span_id


def linked(span: ReadableSpan) -> list[tuple[int, int]]:
    return [(link.context.trace_id, link.context.span_id) for link in span.links]


def attribute(span: ReadableSpan, key: str) -> Any:
    return (span.attributes or {})[key]


def tags(span: ReadableSpan) -> tuple[str, ...]:
    return attribute(span, "langfuse.trace.tags")


async def test_a_run_on_an_agents_write_has_no_user(
    ledger: Ledger, stack: Stack, exporter: InMemorySpanExporter, provider: TracerProvider
) -> None:
    async def noop(reaction: r.Reaction[Outbound]) -> None:
        return None

    anyone = reflexr.Rule(
        name="app:any", when=reflexr.on(ArtifactCreated), then=reflexr.run("noop")
    )
    app = stack.process(
        ledger,
        rules=[anyone],
        actions={"noop": noop},
        tracer_provider=provider,
        run_context=bridged_run,
    )
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    client = alice.as_actor(a.ExternalAgentActor(client_id="mcp"))
    await client.create(Note(text=""))
    await bridged(stack, 1)
    await app.reactor.settle()
    [run] = await finished(exporter, "invoke_workflow app:any")
    assert "user.id" not in (run.attributes or {})
    assert not any(tag.startswith("thread:") for tag in tags(run))


@pytest.mark.parametrize(
    ("actor", "rule"),
    [(ALICE, None), (a.ExternalAgentActor(client_id="reflexr:app:fake"), "app:fake")],
    ids=["a person", "a rule's actor with no run behind it"],
)
async def test_a_turn_not_started_by_a_rules_run_has_no_chain(
    ledger: Ledger,
    exporter: InMemorySpanExporter,
    runner: artifactr.agent.Runner[None],
    actor: a.Actor,
    rule: str | None,
) -> None:
    workspace = await artifactr.Workspaces(artifactr.InMemoryStorage()).open(*KEY, actor=actor)
    thread = await workspace.create_thread()
    sent = await runner.send(workspace, thread.id, "hello")
    assert sent.run is not None
    await sent.run.wait()
    [turn] = await finished(exporter, "invoke_workflow turn")
    expected = ["tenant:acme", "workspace:prod", *([f"rule:{rule}"] if rule else [])]
    assert list(tags(turn)) == expected


async def test_a_follower_traces_nothing_of_what_first_opened_its_workspace(
    ledger: Ledger, stack: Stack, exporter: InMemorySpanExporter, provider: TracerProvider
) -> None:
    app = stack.process(ledger, tracer_provider=provider)
    request = provider.get_tracer("the application")
    with (
        request.start_as_current_span("POST /artifactr/v1/commands"),
        propagate_attributes(tags=["request:tag"], user_id="bob"),
    ):
        alice = await app.collaboration.open(*KEY, actor=ALICE)  # starts the follower
        thread = await alice.create_thread()
        await alice.post_message(thread.id, "hello")
    await bridged(stack, 1)
    [bridge] = await finished(exporter, "relayr.bridge message_posted")
    assert bridge.parent is None, "a trace of its own"
    assert not any(key.startswith("langfuse.") for key in bridge.attributes or {})
    assert "user.id" not in (bridge.attributes or {})
