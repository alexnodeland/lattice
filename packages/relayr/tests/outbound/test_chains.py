"""How the follower carries a rule's causal chain back into reflexr, and where it stops."""

import pytest

import artifactr
import artifactr.core as a
import reflexr
import reflexr.workspace as r
from relayr.ledger import Cause, Ledger
from relayr.outbound import Allowlist, Outbound, RunActions, rule_actor
from tests.app_types import Note
from tests.outbound.test_actions import ACTOR, act, people
from tests.stack import ALICE, KEY, Stack, bridged


async def test_a_persons_answer_to_a_rules_proposal_joins_its_chain(
    ledger: Ledger, stack: Stack
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.create(Note(text="draft"))
        return reaction.run.correlation_id

    [chain] = (await act(stack, ledger, body)).results
    workspace = await people(stack)
    [proposal] = await workspace.proposals()
    await workspace.commit(a.RespondToProposal(proposal_id=proposal.id, decision="accept"))
    await bridged(stack, 4)
    _, proposed, resolved, created = await stack.bridged()
    assert (proposed.correlation_id, proposed.depth) == (chain, 1)
    assert (resolved.correlation_id, resolved.depth) == (chain, 0)
    assert (created.correlation_id, created.depth) == (chain, 0)


async def test_an_answer_to_anyone_elses_proposal_starts_a_chain(
    ledger: Ledger, stack: Stack
) -> None:
    app = stack.process(ledger, rules=[])
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    agent = alice.as_actor(a.ExternalAgentActor(client_id="mcp"))
    proposed = await agent.commit(a.ProposeChange(change=a.create_artifact(Note(text=""))))
    await alice.commit(a.RespondToProposal(proposal_id=proposed.proposal_id, decision="reject"))
    await bridged(stack, 2)
    [_, resolved] = await stack.bridged()
    assert resolved.depth == 0
    assert resolved.correlation_id == resolved.id


async def test_a_chain_continued_past_the_depth_limit_is_dead_lettered(
    ledger: Ledger, stack: Stack
) -> None:
    deep = Cause(correlation_id="evt_first", firing_id="fir_1", run_id="fir_1", depth=99)
    await ledger.record_cause(KEY, "message", "msg_deep", deep)
    app = stack.process(ledger, rules=[])
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    await alice.post_message(thread.id, "deep", message_id="msg_deep")
    await alice.post_message(thread.id, "next")
    await bridged(stack, 1)
    [letter] = await ledger.dead_letters(KEY)
    assert letter.error.startswith("DepthExceeded")


async def turn_for(
    stack: Stack,
    ledger: Ledger,
    said: list[str],
    *,
    impostor: bool = False,
    traced: int | None = None,
) -> list[reflexr.Envelope]:
    """Start a turn for a rule's actor, after it said `said`, and bridge the turn's end.

    The runs behind the first `traced` messages are recorded; all of them by default, or none
    for an impostor's.
    """
    app = stack.process(ledger, rules=[])
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    rule = alice.as_actor(ACTOR)
    message_ids = tuple(f"msg_{content}" for content in said)
    recorded = 0 if impostor else len(said) if traced is None else traced
    for index, (content, message_id) in enumerate(zip(said, message_ids, strict=True)):
        if index < recorded:
            cause = Cause(correlation_id="evt_c", firing_id="fir_c", run_id="fir_c", depth=2)
            await ledger.record_cause(KEY, "message", message_id, cause)
        await rule.post_message(thread.id, content, message_id=message_id)
    agent = alice.as_actor(a.AgentActor(thread_id=thread.id, run_id="run_t", on_behalf_of=ACTOR))
    await agent.record(a.RunStarted(run_id="run_t", thread_id=thread.id, message_ids=message_ids))
    await agent.record(a.RunEnded(run_id="run_t", thread_id=thread.id, status="completed"))
    await bridged(stack, len(said) + 1)
    return [e for e in await stack.bridged() if e.event_type == "artifactr:turn_ended"][-1:]


async def test_a_turn_for_a_rule_continues_the_chain_of_its_last_message(
    ledger: Ledger, stack: Stack
) -> None:
    [ended] = await turn_for(stack, ledger, ["hello", "again"])
    assert ended.depth == 2


async def test_a_turn_continues_the_chain_of_its_last_traced_message(
    ledger: Ledger, stack: Stack
) -> None:
    [ended] = await turn_for(stack, ledger, ["hello", "untraced"], traced=1)
    assert ended.depth == 2


@pytest.mark.parametrize(
    ("said", "impostor"), [([], False), (["hello"], True)], ids=["nothing said", "an impostor"]
)
async def test_a_turn_for_a_rule_without_a_traced_message_starts_a_chain(
    ledger: Ledger, stack: Stack, said: list[str], impostor: bool
) -> None:
    [ended] = await turn_for(stack, ledger, said, impostor=impostor)
    assert ended.depth == 0


async def answer_to(stack: Stack, ledger: Ledger, *, rule: bool) -> tuple[str, reflexr.Envelope]:
    """Pause a turn acting for a rule's actor, or for Alice, and bridge Alice's answer to it.

    The rule's turn carries out its message, posted by a run in the chain Alice's first message
    starts. Returns that chain's id, and the bridged answer.
    """
    app = stack.process(ledger, rules=[])
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    await alice.post_message(thread.id, "start")
    await bridged(stack, 1)
    [first] = await stack.bridged()
    if rule:
        cause = Cause(
            correlation_id=first.correlation_id, firing_id="fir_c", run_id="fir_c", depth=2
        )
        await ledger.record_cause(KEY, "message", "msg_ask", cause)
    sender = alice.as_actor(ACTOR) if rule else alice
    await sender.post_message(thread.id, "ask", message_id="msg_ask")
    acting = ACTOR if rule else ALICE
    agent = alice.as_actor(a.AgentActor(thread_id=thread.id, run_id="run_t", on_behalf_of=acting))
    started = a.RunStarted(run_id="run_t", thread_id=thread.id, message_ids=("msg_ask",))
    await agent.record(started)
    request = a.DeferredRequest(tool_call_id="q1", tool_name="ask_user", kind="question")
    await agent.record(a.RunPaused(run_id="run_t", thread_id=thread.id, requests=(request,)))
    await alice.commit(a.AnswerDeferred(run_id="run_t", tool_call_id="q1", answer="Monday"))
    await bridged(stack, 3)
    [answered] = [e for e in await stack.bridged() if e.event_type == "artifactr:deferred_answered"]
    return first.correlation_id, answered


async def test_a_persons_answer_to_a_rules_paused_turn_joins_its_chain(
    ledger: Ledger, stack: Stack
) -> None:
    chain, answered = await answer_to(stack, ledger, rule=True)
    assert (answered.correlation_id, answered.depth) == (chain, 0)


async def test_an_answer_to_anyone_elses_turn_starts_a_chain(ledger: Ledger, stack: Stack) -> None:
    _, answered = await answer_to(stack, ledger, rule=False)
    assert (answered.correlation_id, answered.depth) == (answered.id, 0)


def test_the_rule_actor_is_an_external_agent_for_no_one() -> None:
    assert rule_actor("ops:triage") == artifactr.ExternalAgentActor(
        client_id="reflexr:ops:triage", name="ops:triage"
    )


async def test_a_rules_direct_create_continues_its_chain(ledger: Ledger, stack: Stack) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.create(Note(text="kept"))
        return reaction.run.correlation_id

    direct = {"app:act": Allowlist(direct=frozenset({"note"}))}
    [chain] = (await act(stack, ledger, body, allowlists=direct)).results
    await bridged(stack, 2)
    _, created = await stack.bridged()
    assert (created.event_type, created.correlation_id, created.depth) == (
        "artifactr:artifact_created",
        chain,
        1,
    )
