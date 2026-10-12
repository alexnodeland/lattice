"""What a run does in artifactr through `RunActions`: ids, allowlists, keyed edits, refusals."""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, override

import pytest
from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo

import artifactr
import artifactr.agent
import artifactr.core as a
import artifactr.workspace
import reflexr
import reflexr.workspace as r
from relayr.events import ArtifactCreated, MessagePosted
from relayr.ledger import InMemoryLedger, Ledger
from relayr.outbound import (
    Allowlist,
    NotAllowed,
    Outbound,
    Refused,
    RunActions,
    is_rule_actor,
    rule_actor,
)
from tests.app_types import Note
from tests.stack import ALICE, KEY, Access, Stack, bridged, notices, until

ACTOR = rule_actor("app:act")
DIRECT = Allowlist(direct=frozenset({"note"}))

type Body = Callable[[RunActions, r.Reaction[Outbound]], Awaitable[object]]


@dataclass
class Acted:
    """What the run's action did: what it returned, or what it raised, on each attempt."""

    results: list[Any] = field(default_factory=list[Any])
    errors: list[BaseException] = field(default_factory=list[BaseException])


def rule(on: type[reflexr.Event]) -> reflexr.Rule:
    return reflexr.Rule(
        name="app:act",
        when=reflexr.on(on).where(reflexr.F.author.kind.eq("user")),
        then=reflexr.run("act"),
        retry=reflexr.RetryPolicy(max_attempts=1),
    )


async def act(
    stack: Stack,
    ledger: Ledger,
    body: Body,
    *,
    allowlists: Mapping[str, Allowlist] | None = None,
    runner: artifactr.agent.Runner[None] | None = None,
    artifactr_authorize: artifactr.workspace.Authorize | None = None,
    on: type[reflexr.Event] = MessagePosted,
    trigger: Callable[[artifactr.Workspace], Awaitable[object]] | None = None,
    rules: list[reflexr.Rule] | None = None,
) -> Acted:
    """Fire the rule once, from a message Alice posts, and run `body` in its action."""
    acted = Acted()

    async def action(reaction: r.Reaction[Outbound]) -> None:
        try:
            acted.results.append(await body(reaction.deps.acting(reaction), reaction))
        except BaseException as error:
            acted.errors.append(error)
            raise

    app = stack.process(
        ledger,
        rules=rules or [rule(on)],
        actions={"act": action},
        allowlists=allowlists,
        runner=runner,
        artifactr_authorize=artifactr_authorize,
    )
    workspace = await app.collaboration.open(*KEY, actor=ALICE)
    if trigger is None:
        thread = await workspace.create_thread()
        await workspace.post_message(thread.id, "go")
    else:
        await trigger(workspace)
    await bridged(stack, 1)
    await app.reactor.settle()
    return acted


async def people(stack: Stack) -> artifactr.Workspace:
    """Alice's handle, past the followers."""
    return await artifactr.Workspaces(stack.artifactr_storage).open(*KEY, actor=ALICE)


async def test_a_run_proposes_by_default(ledger: Ledger, stack: Stack) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        assert reaction.deps.acting(reaction) is acting, "one per attempt"
        return await acting.create(Note(text="draft"), rationale="asked")

    [proposed] = (await act(stack, ledger, body)).results
    [proposal] = await (await people(stack)).proposals()
    assert (proposal.proposed_by, proposal.rationale) == (ACTOR, "asked")
    assert isinstance(proposal.change, a.CreateArtifact)
    assert proposal.change.artifact_id == proposed


async def test_a_keyed_edit_is_skipped_when_its_value_is_in_place(
    ledger: Ledger, stack: Stack
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        note = await acting.create(Note(text=""))
        await acting.edit(note, "/text", "hello", summary="greeted")
        await acting.edit(note, "/text", "hello")
        return note

    [note] = (await act(stack, ledger, body, allowlists={"app:act": DIRECT})).results
    workspace = await people(stack)
    assert isinstance(note, str)
    assert [v.version for v in await workspace.revisions(note)] == [1, 2]
    edited = await workspace.get(Note, note)
    assert (edited.data.text, edited.updated_by) == ("hello", ACTOR)
    await bridged(stack, 3)
    [*_, changed] = await stack.bridged()
    assert (changed.event_type, changed.depth) == ("artifactr:artifact_changed", 1)


async def created_by_alice(workspace: artifactr.Workspace) -> object:
    return await workspace.create(Note(text=""), artifact_id="art_alice")


async def test_a_keyed_edit_is_a_proposal_by_default(ledger: Ledger, stack: Stack) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.edit("art_alice", "/text", "hello", rationale="why")
        return None

    await act(stack, ledger, body, on=ArtifactCreated, trigger=created_by_alice)
    [proposal] = await (await people(stack)).proposals()
    assert proposal.rationale == "why"


def changing(storage: artifactr.InMemoryStorage, times: int) -> artifactr.workspace.Authorize:
    """A hook that has Alice change the note just before each of the rule's edits."""
    changes = iter(range(times))

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: a.Actor, access: Access
    ) -> bool:
        if actor == ACTOR and access.action == "artifactr:edit_artifact":
            for n in changes:
                alice = await artifactr.Workspaces(storage).open(*KEY, actor=ALICE)
                current = await alice.get(Note, "art_alice")
                patch = a.JsonPatch(ops=({"op": "replace", "path": "/text", "value": str(n)},))
                edit = a.EditArtifact(
                    artifact_id="art_alice", base_version=current.version, patch=patch
                )
                await alice.commit(edit)
                break
        return True

    return authorize


async def test_an_edit_is_made_again_after_a_version_conflict(ledger: Ledger, stack: Stack) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.edit("art_alice", "/text", "mine")
        return None

    acted = await act(
        stack,
        ledger,
        body,
        allowlists={"app:act": DIRECT},
        artifactr_authorize=changing(stack.artifactr_storage, 1),
        on=ArtifactCreated,
        trigger=created_by_alice,
    )
    assert acted.errors == []
    assert (await (await people(stack)).get(Note, "art_alice")).data.text == "mine"


async def test_an_edit_whose_artifact_keeps_changing_fails_the_attempt(
    ledger: Ledger, stack: Stack
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.edit("art_alice", "/text", "mine")
        return None

    acted = await act(
        stack,
        ledger,
        body,
        allowlists={"app:act": DIRECT},
        artifactr_authorize=changing(stack.artifactr_storage, 3),
        on=ArtifactCreated,
        trigger=created_by_alice,
    )
    [error] = acted.errors
    assert isinstance(error, r.RunFailure)
    assert (error.reason, error.permanent) == ("version_conflict", False)


async def archived_by_alice(workspace: artifactr.Workspace) -> object:
    await workspace.create(Note(text=""), artifact_id="art_alice")
    return await workspace.commit(a.ArchiveArtifact(artifact_id="art_alice", base_version=1))


@pytest.mark.parametrize(
    ("body", "reason", "permanent"),
    [
        (lambda acting: acting.read("art_missing"), "not_found", False),
        (lambda acting: acting.edit("art_alice", "/nowhere/deep", "x"), "patch_failed", False),
        (lambda acting: acting.edit("art_alice", "/text", "x"), "invalid_state", True),
    ],
)
@pytest.mark.parametrize("allowlist", [DIRECT, Allowlist()], ids=["direct", "proposed"])
async def test_what_artifactr_refuses_fails_the_run(
    ledger: Ledger,
    stack: Stack,
    body: Callable[[RunActions], Awaitable[object]],
    reason: str,
    permanent: bool,
    allowlist: Allowlist,
) -> None:
    acted = await act(
        stack,
        ledger,
        lambda acting, reaction: body(acting),
        allowlists={"app:act": allowlist},
        on=ArtifactCreated,
        trigger=archived_by_alice if reason == "invalid_state" else created_by_alice,
    )
    [error] = acted.errors
    assert isinstance(error, r.RunFailure)
    assert isinstance(error, Refused) is not permanent
    assert (error.reason, error.permanent) == (reason, permanent)
    assert await (await people(stack)).proposals() == [], "nothing was proposed"


async def test_a_refused_write_fails_the_run_for_good(ledger: Ledger, stack: Stack) -> None:
    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: a.Actor, access: Access
    ) -> bool:
        return access.action != "artifactr:propose_change"

    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        return await acting.create(Note(text=""))

    [error] = (await act(stack, ledger, body, artifactr_authorize=authorize)).errors
    assert isinstance(error, r.RunFailure)
    assert error.reason == "forbidden"


async def test_a_run_acts_only_in_its_chains_threads_unless_allowed(
    ledger: Ledger, stack: Stack
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.notice("here")
        with pytest.raises(NotAllowed, match="only in its chain's threads"):
            await acting.notice("there", thread_id="thr_other")
        with pytest.raises(NotAllowed, match="may not create threads"):
            await acting.create_thread("mine")
        return reaction.events[0].event.model_dump()["thread_id"]

    acted = await act(stack, ledger, body)
    [thread] = acted.results
    assert acted.errors == []
    assert notices(await stack.log()) == [(ACTOR, "here")]
    assert thread


async def test_a_run_allowed_threads_creates_and_acts_in_them(ledger: Ledger, stack: Stack) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        with pytest.raises(NotAllowed, match="no thread"):
            await acting.notice("nowhere")
        thread = await acting.create_thread("incident")
        await acting.notice("opened", thread_id=thread)
        return thread

    allowed = Allowlist(create_threads=True)
    [thread] = (
        await act(
            stack,
            ledger,
            body,
            allowlists={"app:act": allowed},
            on=ArtifactCreated,
            trigger=created_by_alice,
        )
    ).results
    workspace = await people(stack)
    assert (await workspace.thread(str(thread))).title == "incident"


@pytest.mark.parametrize(
    ("allowlists", "allowed"),
    [
        ({"app:act": Allowlist(threads="any")}, True),
        ({"app:*": Allowlist(threads="any")}, True),
        ({"app:act": Allowlist(), "app:*": Allowlist(threads="any")}, False),
        ({"other:*": Allowlist(threads="any")}, False),
        ({"ap:*": Allowlist(threads="any")}, False),
        ({"apps:*": Allowlist(threads="any")}, False),
    ],
    ids=[
        "its own",
        "its namespace's",
        "its own before its namespace's",
        "another namespace's",
        "a shorter namespace's",
        "a longer namespace's",
    ],
)
async def test_a_rule_takes_its_own_allowlist_else_its_namespaces(
    ledger: Ledger, stack: Stack, allowlists: dict[str, Allowlist], allowed: bool
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        return await acting.notice("there", thread_id="thr_elsewhere")

    acted = await act(stack, ledger, body, allowlists=allowlists, trigger=elsewhere)
    if allowed:
        assert acted.errors == []
    else:
        [error] = acted.errors
        assert isinstance(error, NotAllowed)


@pytest.mark.parametrize(
    "key",
    ["*", "app:act*", "app:*:x", "App:*", "reflexr:*", "chat:**", "*:x", "chat", "reflexr:run"],
)
def test_an_allowlist_key_is_a_rule_or_a_whole_namespace(key: str) -> None:
    workspaces = artifactr.Workspaces(artifactr.InMemoryStorage())
    with pytest.raises(ValueError, match=f"not '{re.escape(key)}'"):
        Outbound(workspaces, InMemoryLedger(), allowlists={key: Allowlist()})


async def elsewhere(workspace: artifactr.Workspace) -> object:
    await workspace.commit(a.CreateThread(thread_id="thr_elsewhere"))
    thread = await workspace.create_thread()
    return await workspace.post_message(thread.id, "go")


async def test_ids_are_numbered_afresh_after_a_checkpoint(ledger: Ledger, stack: Stack) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        first = await acting.notice("one")
        await reaction.checkpoint("half", None)
        return first, await acting.notice("two")

    [(first, second)] = (await act(stack, ledger, body)).results
    assert first != second


def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("On it.")])


@pytest.fixture
async def runner() -> AsyncIterator[artifactr.agent.Runner[None]]:
    """A runner whose agent answers every turn at once."""
    agent = Agent(
        artifactr.agent.function_model(reply),
        deps_type=artifactr.agent.Session[None],
        capabilities=[artifactr.agent.ArtifactWorkspace(types=[Note])],
    )
    started = artifactr.agent.Runner(agent, app=None)
    yield started
    await started.aclose()


async def send(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
    return await acting.send("please look")


async def test_a_run_starts_no_turn_unless_its_allowlist_allows(
    ledger: Ledger, stack: Stack, runner: artifactr.agent.Runner[None]
) -> None:
    [error] = (await act(stack, ledger, send, runner=runner)).errors
    assert isinstance(error, NotAllowed)


async def test_a_run_starts_no_turn_without_a_runner(ledger: Ledger, stack: Stack) -> None:
    turns = {"app:act": Allowlist(turns=True)}
    [error] = (await act(stack, ledger, send, allowlists=turns)).errors
    assert isinstance(error, NotAllowed)


async def noted_in_a_thread(workspace: artifactr.Workspace) -> object:
    thread = await workspace.create_thread()
    return await workspace.create(Note(text=""), thread_id=thread.id)


async def test_a_turn_a_rules_message_started_continues_its_chain(
    ledger: Ledger, stack: Stack, runner: artifactr.agent.Runner[None]
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.send("please look")
        return reaction.run.correlation_id

    turns = {"app:act": Allowlist(turns=True)}
    [chain] = (
        await act(
            stack,
            ledger,
            body,
            allowlists=turns,
            runner=runner,
            on=ArtifactCreated,
            trigger=noted_in_a_thread,
        )
    ).results

    async def ended() -> bool:
        return any(e.event_type == "artifactr:turn_ended" for e in await stack.bridged())

    await until(ended)
    _, sent, reply, turn_ended = await stack.bridged()
    assert isinstance(sent.event, MessagePosted)
    assert sent.event.author == ACTOR
    for continued in (sent, reply, turn_ended):
        assert (continued.correlation_id, continued.depth) == (chain, 1)


async def test_a_turn_for_a_person_starts_a_chain_of_its_own(
    ledger: Ledger, stack: Stack, runner: artifactr.agent.Runner[None]
) -> None:
    turns = {"app:act": Allowlist(turns=True)}
    await act(stack, ledger, send, allowlists=turns, runner=runner)

    async def turns_ended() -> list[reflexr.Envelope]:
        return [e for e in await stack.bridged() if e.event_type == "artifactr:turn_ended"]

    async def both() -> bool:
        return len(await turns_ended()) == 2

    await until(both)
    alices, rules = await turns_ended()
    assert (alices.depth, rules.depth) == (0, 1), "Alice's message is carried out first"


async def test_a_refused_turn_fails_the_run_for_good(
    ledger: Ledger, stack: Stack, runner: artifactr.agent.Runner[None]
) -> None:
    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: a.Actor, access: Access
    ) -> bool:
        return not (actor == ACTOR and access.action == "artifactr:post_message")

    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        return await acting.send("please look")

    turns = {"app:act": Allowlist(turns=True)}
    [error] = (
        await act(
            stack, ledger, body, allowlists=turns, runner=runner, artifactr_authorize=authorize
        )
    ).errors
    assert isinstance(error, r.RunFailure)
    assert error.reason == "forbidden"


async def test_a_retried_run_sends_its_message_once(
    ledger: Ledger, stack: Stack, runner: artifactr.agent.Runner[None]
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        await acting.send("please look")
        if reaction.attempt == 1:
            raise RuntimeError("the attempt fails after sending")
        return reaction.attempt

    retried = reflexr.Rule(
        name="app:act",
        when=reflexr.on(ArtifactCreated).where(reflexr.F.author.kind.eq("user")),
        then=reflexr.run("act"),
        retry=reflexr.RetryPolicy(max_attempts=2, backoff=timedelta(milliseconds=1)),
    )
    turns = {"app:act": Allowlist(turns=True)}
    acted = await act(
        stack,
        ledger,
        body,
        allowlists=turns,
        runner=runner,
        rules=[retried],
        trigger=noted_in_a_thread,
    )
    await asyncio.sleep(0.01)
    await stack.processes[-1].reactor.settle()
    assert acted.results == [2]
    sent = [e for e in await stack.log() if e.actor == ACTOR]
    assert len(sent) == 1


class StopsAfterPosting(artifactr.agent.Runner[None]):
    """A runner whose first `send` posts its message, then stops before it asks for a turn."""

    def __init__(self, agent: Agent[artifactr.agent.Session[None], str]) -> None:
        super().__init__(agent, app=None)
        self.stopped = False

    @override
    async def send(
        self,
        workspace: artifactr.Workspace,
        thread_id: a.ThreadId,
        content: str,
        *,
        message_id: a.MessageId | None = None,
    ) -> artifactr.agent.Sent:
        if self.stopped:
            return await super().send(workspace, thread_id, content, message_id=message_id)
        self.stopped = True
        await workspace.post_message(thread_id, content, message_id=message_id)
        raise RuntimeError("the process stopped before it asked for the turn")


async def test_a_retry_asks_for_the_turn_an_earlier_attempt_never_asked_for(
    ledger: Ledger, stack: Stack
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        return await acting.send("please look")

    retried = reflexr.Rule(
        name="app:act",
        when=reflexr.on(ArtifactCreated).where(reflexr.F.author.kind.eq("user")),
        then=reflexr.run("act"),
        retry=reflexr.RetryPolicy(max_attempts=2, backoff=timedelta(milliseconds=1)),
    )
    agent = Agent(
        artifactr.agent.function_model(reply),
        deps_type=artifactr.agent.Session[None],
        capabilities=[artifactr.agent.ArtifactWorkspace(types=[Note])],
    )
    runner = StopsAfterPosting(agent)
    turns = {"app:act": Allowlist(turns=True)}
    try:
        await act(
            stack,
            ledger,
            body,
            allowlists=turns,
            runner=runner,
            rules=[retried],
            trigger=noted_in_a_thread,
        )

        async def answered() -> bool:
            await stack.processes[-1].reactor.settle()  # the retry, once its backoff passes
            return any(e.event_type == "artifactr:turn_ended" for e in await stack.bridged())

        await until(answered)
    finally:
        await runner.aclose()
    [started] = [e.event for e in await stack.log() if isinstance(e.event, a.RunStarted)]
    [sent] = [e.event for e in await stack.log() if e.actor == ACTOR]
    assert isinstance(sent, a.MessagePosted)
    assert started.message_ids == (sent.message_id,)
    [ended] = [e for e in await stack.bridged() if e.event_type == "artifactr:turn_ended"]
    assert ended.depth > 0, "the turn continues the run's chain"


async def test_a_retried_runs_writes_are_each_made_once(ledger: Ledger, stack: Stack) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        thread = await acting.create_thread("incident")
        await acting.edit("art_alice", "/text", "proposed")
        await acting.create(Note(text="new"))
        await acting.notice("noted")
        if reaction.attempt == 1:
            raise RuntimeError("the attempt fails after acting")
        return thread

    retried = reflexr.Rule(
        name="app:act",
        when=reflexr.on(ArtifactCreated).where(reflexr.F.author.kind.eq("user")),
        then=reflexr.run("act"),
        retry=reflexr.RetryPolicy(max_attempts=2, backoff=timedelta(milliseconds=1)),
    )
    acted = await act(
        stack,
        ledger,
        body,
        allowlists={"app:act": Allowlist(create_threads=True)},
        rules=[retried],
        trigger=created_by_alice,
    )
    await asyncio.sleep(0.01)
    await stack.processes[-1].reactor.settle()
    [thread] = acted.results
    workspace = await people(stack)
    assert len(await workspace.proposals()) == 2, "the edit's and the create's, once each"
    assert [t.id for t in await workspace.threads()] == [thread]
    assert notices(await stack.log()) == [(ACTOR, "noted")]


def archiving(storage: artifactr.InMemoryStorage) -> artifactr.workspace.Authorize:
    """A hook that has Alice archive the note just before the rule proposes its edit."""

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: a.Actor, access: Access
    ) -> bool:
        if actor == ACTOR and access.action == "artifactr:propose_change":
            alice = await artifactr.Workspaces(storage).open(*KEY, actor=ALICE)
            await alice.commit(a.ArchiveArtifact(artifact_id="art_alice", base_version=1))
        return True

    return authorize


async def test_an_edit_of_an_artifact_archived_meanwhile_fails_for_good(
    ledger: Ledger, stack: Stack
) -> None:
    async def body(acting: RunActions, reaction: r.Reaction[Outbound]) -> object:
        return await acting.edit("art_alice", "/text", "x")

    [error] = (
        await act(
            stack,
            ledger,
            body,
            artifactr_authorize=archiving(stack.artifactr_storage),
            on=ArtifactCreated,
            trigger=created_by_alice,
        )
    ).errors
    assert isinstance(error, r.RunFailure)
    assert (error.reason, error.permanent) == ("invalid_state", True)


def test_a_rules_actor_acts_for_no_person() -> None:
    person = a.UserActor(id="bob")
    assert is_rule_actor(rule_actor("app:triage"))
    assert not is_rule_actor(rule_actor("app:triage").model_copy(update={"on_behalf_of": person}))
    assert not is_rule_actor(a.ExternalAgentActor(client_id="ci"))
