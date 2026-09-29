"""Commands through the runner: carried out once per id, and described to models."""

from artifactr.agent import (
    CommandKey,
    InMemoryCommandResults,
    describe_outcome,
    list_artifacts_text,
)
from artifactr.core import (
    Applied,
    CommandResult,
    CreateThread,
    Proposed,
    Recorded,
    Resolved,
    Thread,
    UserActor,
)
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import Gate, Script, make_agent, make_runner, say
from tests.artifact_types import Note


async def test_a_command_is_carried_out_once_per_id(ws: Workspace, gate: Gate) -> None:
    runner = make_runner(make_agent(Script()), gate)
    first = await runner.execute_once(ws, CreateThread(thread_id="t1"), command_id="c1")
    assert first.ok
    assert first.outcome == Recorded(seq=1)
    again = await runner.execute_once(ws, CreateThread(thread_id="t1"), command_id="c1")
    assert again == first, "the first result, and the thread was not created twice"
    rejected = await runner.execute_once(ws, CreateThread(thread_id="t1"), command_id="c2")
    assert rejected.rejection is not None
    assert rejected.rejection["type"] == "invalid_state"
    other = await runner.execute_once(ws, CreateThread(thread_id="t2"), command_id="c2")
    assert other == rejected, "the id alone names the command, and a rejection is remembered"
    assert [t.id for t in await ws.threads()] == ["t1"]


async def test_the_same_id_elsewhere_or_from_someone_else_is_another_command(
    storage: InMemoryStorage, ws: Workspace, gate: Gate
) -> None:
    runner = make_runner(make_agent(Script()), gate)
    workspaces = Workspaces(storage)
    alice_again = ws.as_actor(UserActor(id="alice", name="Alice, renamed"))
    senders = [
        ws.as_actor(UserActor(id="bob")),  # another participant
        await workspaces.open("tenant", "elsewhere", actor=ws.actor),  # another workspace
        await workspaces.open("another", "ws", actor=ws.actor),  # another tenant's "ws"
    ]
    await runner.execute_once(ws, CreateThread(thread_id="t1"), command_id="c1")
    for sender in senders:
        result = await runner.execute_once(sender, CreateThread(thread_id="t2"), command_id="c1")
        assert result.ok, sender
    repeated = await runner.execute_once(alice_again, CreateThread(thread_id="t3"), command_id="c1")
    assert repeated.outcome == Recorded(seq=1), "the same participant, whatever its name"
    assert [t.id for t in await ws.threads()] == ["t1", "t2"]


async def test_only_the_most_recent_results_are_remembered() -> None:
    results = InMemoryCommandResults(capacity=1)
    first, second = (CommandKey("tenant", "ws", "user:alice", c) for c in ("c1", "c2"))
    result = CommandResult(command_id="c1", ok=True, outcome=Recorded())
    await results.put(first, result)
    assert await results.get(first) == result
    await results.put(second, result)
    assert await results.get(first) is None, "the oldest is forgotten"
    assert await results.get(second) == result


async def test_a_message_names_the_run_it_started(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    runner = make_runner(make_agent(Script(say("On it."))), gate)
    async with ws.claim_thread(thread.id, holder="another process"):
        steered = await runner.send(ws, thread.id, "Also this")
    assert (steered.run, steered.outcome.run_id) == (None, None), "it steered the active run"
    sent = await runner.send(ws, thread.id, "Plan it")
    assert sent.run is not None
    assert sent.outcome.run_id == sent.run.run_id
    await sent.run.wait()


def test_outcomes_are_described_for_models() -> None:
    assert describe_outcome(Applied(artifact_id="n1", version=2)) == "Done: n1 is now at version 2."
    assert describe_outcome(Proposed(proposal_id="p1")).startswith("Proposed as p1.")
    accepted = Resolved(proposal_id="p1", decision="accept", version=3)
    assert describe_outcome(accepted) == "Accepted p1: the artifact is now at version 3."
    rejected = Resolved(proposal_id="p1", decision="reject")
    assert describe_outcome(rejected) == "Rejected p1."
    assert describe_outcome(Recorded()) == "Done."


async def test_archived_artifacts_are_listed_on_request(ws: Workspace) -> None:
    await ws.create(Note(text="kept"), artifact_id="n1")
    await ws.create(Note(text="old"), artifact_id="n2")
    await ws.commit((await ws.artifact("n2")).archive())
    assert await list_artifacts_text(ws) == "- n1 (note, v1)"
    listed = await list_artifacts_text(ws, "note", include_archived=True)
    assert listed == "- n1 (note, v1)\n- n2 (note, v2, archived)"
