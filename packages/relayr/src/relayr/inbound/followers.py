"""Followers: one per workspace, publishing its artifactr envelopes into reflexr, in `seq` order.

A follower opens the workspace in both libraries, with the same tenant and id. It holds the
workspace's lease in the ledger, so one process at a time follows it, and renews the lease while
it follows. It reads the artifactr log after its cursor, projects each envelope, publishes the
event with the envelope's id, and only then moves its cursor. reflexr's `publish` appends an id
once, so an envelope delivered again, after a restart or by another process, publishes nothing
new: delivery is at least once, and the effect exactly once.

A rule's run that wrote an envelope, or started the turn that did, continues its causal chain
into reflexr one step deeper, so rules that answer each other stop at reflexr's depth limit. A
person's answer to a rule's proposal joins the proposal's chain without going deeper.

An envelope is dead-lettered in the ledger, and the follower moves on, when its projection raises,
an invalid event included, returns one of reflexr's own events, or would continue its chain past
the depth limit. Anything else
stops the follower, a type reflexr doesn't accept included, since that is the application's
configuration and every later envelope would meet it too. A stopped follower starts again, at its
cursor, the next time its workspace is opened.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Final

import artifactr
import artifactr.core
import reflexr.workspace
from reflexr import SourceActor, new_id
from reflexr.core import Causation, DepthExceeded, Forbidden
from relayr.events import Projections
from relayr.ledger import CauseKind, DeadLetter, Ledger, WorkspaceKey
from relayr.outbound import is_rule_actor

logger = logging.getLogger("relayr.inbound")


FOLLOWER: Final = artifactr.SystemActor(name="relayr")
"""Who a follower reads artifactr's log as."""

SOURCE: Final = SourceActor(name="artifactr")
"""Who a follower publishes into reflexr as: the actor on every bridged envelope."""


class Followers:
    """Follows each workspace the application uses, from the first time it is opened.

    Give [`watch`][relayr.inbound.Followers.watch] to both libraries' `Workspaces` as their
    `on_open`, composed with any other, and call [`resume`][relayr.inbound.Followers.resume] at
    startup to follow again every workspace the ledger knows.

    Args:
        artifactr: The workspaces whose logs are followed.
        reflexr: The workspaces the events are published into. Their `events` must include
            [`BRIDGED`][relayr.events.BRIDGED], and the types the projections publish: a type
            they refuse stops the follower.
        ledger: Where each follower keeps its lease, cursor and dead letters.
        projections: What each envelope becomes. Defaults to the default set alone.
        holder: This process's name in leases. Defaults to a new random id; give each process
            its own.
        lease_ttl: How long a lease lasts unless renewed. A follower renews it every third of
            that, and a process that dies holding one lets another take it once it lapses.
        save_every: How many envelopes that bridge nothing a follower reads before it saves its
            cursor anyway, so a restarted follower reads at most this many again.
        read_back: How many envelopes a follower reads back at a time, looking for the message
            of a rule's that an agent turn carries out.
    """

    def __init__(
        self,
        artifactr: artifactr.Workspaces,
        reflexr: reflexr.workspace.Workspaces,
        ledger: Ledger,
        *,
        projections: Projections | None = None,
        holder: str | None = None,
        lease_ttl: timedelta = timedelta(seconds=30),
        save_every: int = 500,
        read_back: int = 100,
    ) -> None:
        self._artifactr = artifactr
        self._reflexr = reflexr
        self._ledger = ledger
        self._projections = projections or Projections()
        self._holder = holder or new_id("relayr")
        self._ttl = lease_ttl
        self._save_every = save_every
        self._read_back = read_back
        self._tasks: dict[WorkspaceKey, asyncio.Task[None]] = {}
        self._closed = False

    async def watch(self, tenant_id: str, workspace_id: str) -> None:
        """Follow a workspace, unless it is followed already: the libraries' `on_open` hook.

        It is called each time a workspace is opened, its follower's own openings included, so
        it does nothing for a workspace it follows already, nor once the followers are closed.
        """
        workspace = WorkspaceKey(tenant_id, workspace_id)
        if self._closed or workspace in self._tasks:
            return
        task = asyncio.create_task(self._follow(workspace))
        self._tasks[workspace] = task
        task.add_done_callback(lambda done: self._ended(workspace, done))

    async def resume(self) -> None:
        """Follow every workspace the ledger knows: call it when the application starts."""
        for workspace in await self._ledger.followed():
            await self.watch(*workspace)

    async def aclose(self) -> None:
        """Stop every follower, releasing its lease, and start no more."""
        self._closed = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _ended(self, workspace: WorkspaceKey, task: asyncio.Task[None]) -> None:
        # A follower that stopped starts again the next time its workspace is opened.
        self._tasks.pop(workspace, None)
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("following %s/%s stopped", *workspace, exc_info=error)

    async def _follow(self, workspace: WorkspaceKey) -> None:
        """Follow a workspace whenever this process holds its lease, until cancelled."""
        source = await self._artifactr.open(*workspace, actor=FOLLOWER)
        target = await self._reflexr.open(*workspace, actor=SOURCE)
        while True:
            if await self._ledger.acquire_lease(workspace, self._holder, self._ttl):
                try:
                    await self._hold(workspace, source, target)
                finally:
                    await self._ledger.release_lease(workspace, self._holder)
            await asyncio.sleep(self._ttl.total_seconds() / 3)

    async def _hold(
        self,
        workspace: WorkspaceKey,
        source: artifactr.Workspace,
        target: reflexr.workspace.Workspace,
    ) -> None:
        """Relay the workspace's envelopes while the lease holds; return once it is lost.

        The renewal cancels the relaying when it loses the lease, or fails, so the lease is never
        held with nothing relayed.
        """
        relaying = asyncio.current_task()
        assert relaying is not None, "a follower runs as a task"
        renewal = asyncio.create_task(self._renew(workspace, relaying))
        try:
            await self._relay(workspace, source, target)
        except asyncio.CancelledError:
            if not renewal.done() or relaying.uncancel():
                raise  # cancelled from outside
            renewal.result()  # the renewal's error, if it failed; else the lease is lost
        finally:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)

    async def _renew(self, workspace: WorkspaceKey, relaying: asyncio.Task[None]) -> None:
        """Renew the lease every third of its life; cancel the relaying once it is lost or fails."""
        try:
            while True:
                await asyncio.sleep(self._ttl.total_seconds() / 3)
                if not await self._ledger.acquire_lease(workspace, self._holder, self._ttl):
                    break
        except Exception:
            relaying.cancel()
            raise
        logger.info("the lease on %s/%s went to another holder", *workspace)
        relaying.cancel()

    async def _relay(
        self,
        workspace: WorkspaceKey,
        source: artifactr.Workspace,
        target: reflexr.workspace.Workspace,
    ) -> None:
        saved = await self._ledger.cursor(workspace)
        async for envelope in source.subscribe(after_seq=saved):
            await self._trace_turn(workspace, source, envelope)
            bridged = await self._bridge(workspace, target, envelope)
            if bridged or envelope.seq - saved >= self._save_every:
                await self._ledger.save_cursor(workspace, envelope.seq)
                saved = envelope.seq

    async def _trace_turn(
        self,
        workspace: WorkspaceKey,
        source: artifactr.Workspace,
        envelope: artifactr.core.Envelope,
    ) -> None:
        """Record the run behind an agent turn that a rule's message started, as it starts.

        A turn acts for the author of the messages it carries out, one author per turn, and
        carries out the oldest messages no turn has taken. So a turn that acts for a rule carries
        out the rule's messages since the rule's last turn in the thread, whatever turns for
        others came between: it continues the chain of the run that posted the last of them.
        Notices start no turn, and are passed over.
        """
        match envelope:
            case artifactr.core.Envelope(
                event=artifactr.core.RunStarted(run_id=turn, thread_id=thread),
                actor=artifactr.core.AgentActor(on_behalf_of=rule),
            ) if rule is not None and is_rule_actor(rule):
                pass
            case _:
                return
        before = envelope.seq
        while page := await source.read(before_seq=before, threads={thread}, last=self._read_back):
            for earlier in reversed(page):
                match earlier.event:
                    case artifactr.core.MessagePosted(kind="message", message_id=message_id) if (
                        earlier.actor == rule
                    ):
                        cause = await self._ledger.cause(workspace, "message", message_id)
                        if cause is not None:
                            await self._ledger.record_cause(workspace, "turn", turn, cause)
                        return
                    case artifactr.core.RunStarted() if _acts_for(earlier.actor, rule):
                        return  # an earlier turn for the rule took what came before it
                    case _:
                        pass
            before = page[0].seq

    async def _bridge(
        self,
        workspace: WorkspaceKey,
        target: reflexr.workspace.Workspace,
        envelope: artifactr.core.Envelope,
    ) -> bool:
        """Publish an envelope's event; return whether it published or dead-lettered one."""
        try:
            event = self._projections.project(envelope)
        except Exception as error:  # a projection is the application's code
            await self._dead_letter(workspace, envelope, error)
            return True
        if event is None:
            return False
        if event.event_namespace == "reflexr":
            refused = Forbidden(f"{event.event_type} events are recorded by reflexr, not published")
            await self._dead_letter(workspace, envelope, refused)
            return True
        publishing, correlation_id = await self._chain(workspace, target, envelope)
        try:
            await publishing.publish(event, id=envelope.id, correlation_id=correlation_id)
        except DepthExceeded as deep:
            await self._dead_letter(workspace, envelope, deep)
        return True

    async def _chain(
        self,
        workspace: WorkspaceKey,
        target: reflexr.workspace.Workspace,
        envelope: artifactr.core.Envelope,
    ) -> tuple[reflexr.workspace.Workspace, str | None]:
        """The handle an envelope's event is published through, and the chain it joins.

        A rule's run behind the envelope (a write it made, or a turn its message started)
        continues its chain, as the run's own events do. A person's answer to a rule's proposal
        joins the proposal's chain without going deeper. Anything else starts a chain of its own.
        """
        cause = None
        if envelope.run_id is not None:
            cause = await self._ledger.cause(workspace, "turn", envelope.run_id)
        written = _written(envelope)
        if cause is None and written is not None:
            cause = await self._ledger.cause(workspace, *written)
        if cause is not None:
            causation = Causation(firing_id=cause.firing_id, run_id=cause.run_id, depth=cause.depth)
            return target.caused_by(causation, correlation_id=cause.correlation_id), None
        answered = _answered(envelope.event)
        if answered is not None:
            proposed = await self._ledger.cause(workspace, "proposal", answered)
            if proposed is not None:
                return target, proposed.correlation_id
        return target, None

    async def _dead_letter(
        self, workspace: WorkspaceKey, envelope: artifactr.core.Envelope, error: Exception
    ) -> None:
        kind = envelope.event.type
        logger.warning(
            "could not bridge %s at seq %d in %s/%s: %r", kind, envelope.seq, *workspace, error
        )
        letter = DeadLetter(
            seq=envelope.seq,
            envelope_id=envelope.id,
            event_type=kind,
            error=f"{type(error).__name__}: {error}",
        )
        await self._ledger.dead_letter(workspace, letter)


def _written(envelope: artifactr.core.Envelope) -> tuple[CauseKind, str] | None:
    """What a rule's run would have recorded this write by, if it made it."""
    match envelope:
        case artifactr.core.Envelope(event=artifactr.core.MessagePosted(message_id=message_id)):
            return "message", message_id
        case artifactr.core.Envelope(event=artifactr.core.ProposalCreated(proposal_id=proposal_id)):
            return "proposal", proposal_id
        case artifactr.core.Envelope(
            event=artifactr.core.ArtifactCreated(proposal_id=None, artifact_id=artifact_id)
        ):
            return "artifact", artifact_id
        case artifactr.core.Envelope(
            event=artifactr.core.ArtifactChanged(
                proposal_id=None, artifact_id=artifact_id, version=version
            ),
            actor=artifactr.core.ExternalAgentActor(client_id=client_id) as actor,
        ) if is_rule_actor(actor):
            return "edit", f"{client_id}/{artifact_id}@{version}"
        case _:
            return None


def _acts_for(actor: artifactr.core.Actor, rule: artifactr.core.Actor) -> bool:
    """Whether an actor is an agent's turn acting for a rule's actor."""
    return isinstance(actor, artifactr.core.AgentActor) and actor.on_behalf_of == rule


def _answered(event: artifactr.core.Event) -> str | None:
    """The proposal an accepted or rejected proposal's events are about."""
    match event:
        case (
            artifactr.core.ProposalResolved(proposal_id=proposal_id)
            | artifactr.core.ArtifactCreated(proposal_id=str() as proposal_id)
            | artifactr.core.ArtifactChanged(proposal_id=str() as proposal_id)
            | artifactr.core.ArtifactArchived(proposal_id=str() as proposal_id)
        ):
            return proposal_id
        case _:
            return None
