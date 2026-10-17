"""The test application: both libraries over shared in-memory storage, relayr between them.

A `Stack` is what outlives a process: the libraries' storage. Each `Process` over it has both
libraries' workspaces, the followers, the outbound adapter and a reactor, as an application does.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import TracerProvider

import artifactr
import artifactr.agent
import artifactr.core as a
import artifactr.workspace
import reflexr
import reflexr.core
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
PATIENCE = 30.0
"""How many seconds a test waits for what it awaits: long enough for a loaded CI runner."""

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
        workspace = await self.reader()
        return [e for e in await workspace.read() if _is_bridged(e)]

    async def until_bridged(self, found: Callable[[list[reflexr.Envelope]], bool]) -> None:
        """Wait until the bridged envelopes so far are what `found` awaits.

        It follows reflexr's log, so it wakes as each envelope commits rather than polling, and
        fails once `PATIENCE` runs out.
        """
        workspace = await self.reader()
        so_far: list[reflexr.Envelope] = []
        try:
            async with asyncio.timeout(PATIENCE), aclosing(workspace.subscribe()) as envelopes:
                async for envelope in envelopes:
                    if _is_bridged(envelope):
                        so_far.append(envelope)
                        if found(so_far):
                            return
        except TimeoutError:
            pytest.fail(
                f"{len(so_far)} envelopes were bridged in {PATIENCE:.0f} s, not those awaited"
            )

    async def reader(self) -> r.Workspace:
        """reflexr's workspace, opened past the followers."""
        reader = r.Workspaces(self.reflexr_storage)
        return await reader.open(TENANT, WORKSPACE, actor=reflexr.SystemActor())

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
        authorize: r.Authorize | None = None,
        artifactr_authorize: artifactr.workspace.Authorize | None = None,
        rules: Sequence[reflexr.Rule] = (GREET,),
        actions: Actions | None = None,
        more_actions: Callable[[Outbound, artifactr.Workspaces], Actions] | None = None,
        stored_rules: reflexr.core.StoredRules | None = None,
        allowlists: Mapping[str, Allowlist] | None = None,
        runner: artifactr.agent.Runner[None] | None = None,
        max_depth: int = 8,
        cause_ttl: timedelta = timedelta(days=7),
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        run_context: r.RunContext | None = None,
    ) -> Process:
        async def on_open(tenant_id: str, workspace_id: str) -> None:
            await bridge.watch(tenant_id, workspace_id)

        async def greet(reaction: r.Reaction[Outbound]) -> None:
            [envelope] = reaction.events
            self.greeted.append(envelope.event.model_dump()["content"])

        collaboration = artifactr.Workspaces(
            self.artifactr_storage,
            authorize=artifactr_authorize,
            on_open=on_open,
            tracer_provider=tracer_provider,
        )
        automation = r.Workspaces(
            self.reflexr_storage,
            events=events,
            rules=rules,
            authorize=authorize,
            max_depth=max_depth,
            stored_rules=stored_rules,
            on_open=on_open,
            tracer_provider=tracer_provider,
        )
        bridge = Followers(
            collaboration,
            automation,
            ledger,
            projections=projections,
            holder=holder,
            lease_ttl=TTL,
            save_every=save_every,
            cause_ttl=cause_ttl,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )
        outbound = Outbound(collaboration, ledger, allowlists=allowlists, runner=runner)
        reactor = r.Reactor(
            automation,
            actions={
                **(actions or {"greet": greet}),
                **(more_actions(outbound, collaboration) if more_actions else {}),
            },
            deps=outbound,
            run_context=run_context,
        )
        process = Process(collaboration, automation, bridge, outbound, reactor)
        self.processes.append(process)
        return process


async def until(check: Callable[[], Awaitable[bool]]) -> None:
    """Wait until `check` holds, looking every 10 ms; fail once `PATIENCE` runs out.

    It is for what the libraries announce no event for, such as a follower's cursor or lease.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PATIENCE
    while not await check():
        if loop.time() >= deadline:
            name = getattr(check, "__name__", repr(check))
            pytest.fail(f"{name} didn't hold within {PATIENCE:.0f} s")
        await asyncio.sleep(0.01)


async def bridged(stack: Stack, count: int) -> None:
    """Wait until at least `count` envelopes are bridged."""
    await stack.until_bridged(lambda so_far: len(so_far) >= count)


def _is_bridged(envelope: reflexr.Envelope) -> bool:
    return envelope.event_type.startswith("artifactr:")


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
