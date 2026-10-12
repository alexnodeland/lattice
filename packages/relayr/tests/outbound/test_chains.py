"""How the follower carries a rule's causal chain back into reflexr, and where it stops."""

import pytest

import artifactr
import artifactr.core as a
import reflexr
import reflexr.workspace as r
from relayr.ledger import Cause, Ledger
from relayr.outbound import Outbound, RunActions, rule_actor
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
    stack: Stack, ledger: Ledger, said: list[str], *, impostor: bool = False, read_back: int = 100
) -> list[reflexr.Envelope]:
    """Start a turn for a rule's actor, after it said `said`, and bridge the turn's end."""
    app = stack.process(ledger, rules=[], read_back=read_back)
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    rule = alice.as_actor(ACTOR)
    for content in said:
        message_id = f"msg_{content}"
        if not impostor:
            cause = Cause(correlation_id="evt_c", firing_id="fir_c", run_id="fir_c", depth=2)
            await ledger.record_cause(KEY, "message", message_id, cause)
        await rule.post_message(thread.id, content, message_id=message_id)
    await alice.post_message(thread.id, "between")
    agent = alice.as_actor(a.AgentActor(thread_id=thread.id, run_id="run_t", on_behalf_of=ACTOR))
    await agent.record(a.RunStarted(run_id="run_t", thread_id=thread.id))
    await agent.record(a.RunEnded(run_id="run_t", thread_id=thread.id, status="completed"))
    await bridged(stack, len(said) + 2)
    return [e for e in await stack.bridged() if e.event_type == "artifactr:turn_ended"]


async def test_a_turn_for_a_rule_continues_the_chain_of_its_last_message(
    ledger: Ledger, stack: Stack
) -> None:
    [ended] = await turn_for(stack, ledger, ["hello", "again"], read_back=1)
    assert ended.depth == 2


@pytest.mark.parametrize(("said", "impostor"), [([], False), (["hello"], True)])
async def test_a_turn_for_a_rule_without_a_traced_message_starts_a_chain(
    ledger: Ledger, stack: Stack, said: list[str], impostor: bool
) -> None:
    [ended] = await turn_for(stack, ledger, said, impostor=impostor)
    assert ended.depth == 0


def test_the_rule_actor_is_an_external_agent_for_no_one() -> None:
    assert rule_actor("ops:triage") == artifactr.ExternalAgentActor(
        client_id="reflexr:ops:triage", name="ops:triage"
    )
