"""The test application: both libraries over shared in-memory storage, relayr between them.

A `Stack` is what outlives a process: the libraries' storage. Each `Process` over it has both
libraries' workspaces, the followers, the outbound adapter and a reactor, as an application does.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta

import pytest

import artifactr
import artifactr.agent
import artifactr.core as a
import artifactr.workspace
import reflexr
import reflexr.workspace as r
from relayr.events import BRIDGED, MessagePosted, Projections
from relayr.inbound import Followers
from relayr.ledger import Ledger, WorkspaceKey
from relayr.outbound import Allowlist, Outbound

type Access = artifactr.workspace.Access | r.Access

TENANT, WORKSPACE = "acme", "prod"
KEY = WorkspaceKey(TENANT, WORKSPACE)
ALICE = a.UserActor(id="alice")
TTL = timedelta(milliseconds=60)

GREET = reflexr.Rule(
    name="app:greet",
    when=reflexr.on(MessagePosted).where(reflexr.F.author.kind.eq("user")),
    then=reflexr.run("greet"),
)


type Actions = Mapping[str, r.Action[Outbound]]


@dataclass
class Process:
    """One process of an application: both libraries, relayr's adapters and a reactor."""

    collaboration: artifactr.Workspaces
    automation: r.Workspaces
    followers: Followers
    outbound: Outbound
    reactor: r.Reactor[Outbound]

    async def post(self, content: str) -> a.Recorded:
        """Post a message as Alice, opening the workspace as people do."""
        return await post(self.collaboration, content)


async def post(collaboration: artifactr.Workspaces, content: str) -> a.Recorded:
    """Post a message as Alice, in a thread of its own."""
    workspace = await collaboration.open(TENANT, WORKSPACE, actor=ALICE)
    thread = await workspace.create_thread()
    return await workspace.post_message(thread.id, content)


def at(outcome: a.Recorded | a.Applied | a.Proposed) -> int:
    """Where in artifactr's log a command's last event is."""
    assert outcome.seq is not None
    return outcome.seq


@dataclass
class Stack:
    """What outlives a process: the libraries' storage, and what the rule's runs did."""

    artifactr_storage: artifactr.InMemoryStorage = field(default_factory=artifactr.InMemoryStorage)
    reflexr_storage: r.InMemoryStorage = field(default_factory=r.InMemoryStorage)
    greeted: list[str] = field(default_factory=list[str])
    processes: list[Process] = field(default_factory=list[Process])

    async def bridged(self) -> list[reflexr.Envelope]:
        """The bridged envelopes in reflexr's log, read past the followers."""
        reader = r.Workspaces(self.reflexr_storage)
        workspace = await reader.open(TENANT, WORKSPACE, actor=reflexr.SystemActor())
        return [e for e in await workspace.read() if e.event_type.startswith("artifactr:")]

    async def log(self) -> list[a.Envelope]:
        """artifactr's log, read past the followers."""
        reader = artifactr.Workspaces(self.artifactr_storage)
        return await (await reader.open(TENANT, WORKSPACE, actor=ALICE)).read()

    def process(
        self,
        ledger: Ledger,
        *,
        holder: str = "p1",
        projections: Projections | None = None,
        events: tuple[type[reflexr.Event], ...] = BRIDGED,
        save_every: int = 500,
        read_back: int = 100,
        authorize: r.Authorize | None = None,
        artifactr_authorize: artifactr.workspace.Authorize | None = None,
        rules: Sequence[reflexr.Rule] = (GREET,),
        actions: Actions | None = None,
        allowlists: Mapping[str, Allowlist] | None = None,
        runner: artifactr.agent.Runner[None] | None = None,
        max_depth: int = 8,
    ) -> Process:
        async def on_open(tenant_id: str, workspace_id: str) -> None:
            await bridge.watch(tenant_id, workspace_id)

        async def greet(reaction: r.Reaction[Outbound]) -> None:
            [envelope] = reaction.events
            self.greeted.append(envelope.event.model_dump()["content"])

        collaboration = artifactr.Workspaces(
            self.artifactr_storage, authorize=artifactr_authorize, on_open=on_open
        )
        automation = r.Workspaces(
            self.reflexr_storage,
            events=events,
            rules=rules,
            authorize=authorize,
            max_depth=max_depth,
            on_open=on_open,
        )
        bridge = Followers(
            collaboration,
            automation,
            ledger,
            projections=projections,
            holder=holder,
            lease_ttl=TTL,
            save_every=save_every,
            read_back=read_back,
        )
        outbound = Outbound(collaboration, ledger, allowlists=allowlists, runner=runner)
        reactor = r.Reactor(automation, actions=actions or {"greet": greet}, deps=outbound)
        process = Process(collaboration, automation, bridge, outbound, reactor)
        self.processes.append(process)
        return process


async def until(check: Callable[[], Awaitable[bool]]) -> None:
    for _ in range(300):
        if await check():
            return
        await asyncio.sleep(0.01)
    pytest.fail("it never happened")


async def bridged(stack: Stack, count: int) -> None:
    async def done() -> bool:
        return len(await stack.bridged()) >= count

    await until(done)


def notices(log: list[a.Envelope]) -> list[tuple[a.Actor, str]]:
    """Who posted each notice in a log, and what it says."""
    found: list[tuple[a.Actor, str]] = []
    for envelope in log:
        match envelope.event:
            case a.MessagePosted(kind="notice", content=content):
                found.append((envelope.actor, content))
            case _:
                pass
    return found
