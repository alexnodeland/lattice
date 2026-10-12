"""The outbound adapter: a run of a rule acts in artifactr, as the rule's own participant.

[`Outbound.acting`][relayr.outbound.Outbound.acting] gives a run its
[`RunActions`][relayr.outbound.RunActions]: create an artifact, make a keyed edit, post a notice,
create a thread, and, if the rule's allowlist grants it, send a message that starts a turn.
Each acts as `ExternalAgentActor(client_id="reflexr:<rule>")`, so artifactr's own rules apply to
it, and none can resolve a proposal.

Every write's ids are derived from the run, its last checkpoint and how many writes it made
since, so a retried attempt makes the same writes with the same ids, and artifactr refuses each
again: a proposal, an artifact, a thread and a message are each made once. An edit sets one
value at one path, and is skipped when the value is in place, so repeating one changes nothing.
Before each write, the ledger records the run behind it, by the ids the follower finds it by, so
the follower continues the run's causal chain when it bridges the write back into reflexr.
"""

import hashlib
import weakref
from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

import artifactr
import artifactr.agent
import artifactr.core as a
from reflexr.core import RuleName
from reflexr.workspace import Reaction, RunFailure
from relayr.events import ArtifactrEvent
from relayr.ledger import Cause, CauseKind, Ledger, WorkspaceKey
from relayr.outbound.allowlist import Allowlist

_TRIES = 3
"""How many times an edit re-reads its artifact after a version conflict, within an attempt."""


class NotAllowed(RunFailure):
    """The rule's allowlist doesn't allow what its run tried. Permanent: a retry would try again."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason="not_allowed", permanent=True)


def rule_actor(rule: RuleName) -> a.ExternalAgentActor:
    """Who a rule's runs act as in artifactr: an external agent of their own, for no person."""
    return a.ExternalAgentActor(client_id=f"reflexr:{rule}", name=rule)


class Outbound:
    """Lets the runs of rules act in artifactr, each within its rule's allowlist.

    Give it to the actions that act in artifactr, as their dependency or through
    [`ArtifactrCapability`][relayr.outbound.ArtifactrCapability].

    Args:
        artifactr: The workspaces runs act in: the same tenant and id as the run's.
        ledger: Where the run behind each write is recorded, for the follower.
        allowlists: Each rule's allowlist, by name. A rule with none gets the default.
        runner: Starts the turns that rules allowed to `send` ask for. Without one, no rule may.
    """

    def __init__(
        self,
        artifactr: artifactr.Workspaces,
        ledger: Ledger,
        *,
        allowlists: Mapping[RuleName, Allowlist] | None = None,
        runner: artifactr.agent.Runner[Any] | None = None,
    ) -> None:
        self._artifactr = artifactr
        self._ledger = ledger
        self._allowlists = dict(allowlists or {})
        self._runner = runner
        self._acting: weakref.WeakKeyDictionary[Reaction[Any], RunActions] = (
            weakref.WeakKeyDictionary()
        )

    def allowlist(self, rule: RuleName) -> Allowlist:
        """Return a rule's allowlist: its own, or the default."""
        return self._allowlists.get(rule, Allowlist())

    def acting(self, reaction: Reaction[Any]) -> "RunActions":
        """Return what an attempt of a run may do in artifactr; the same for the whole attempt."""
        actions = self._acting.get(reaction)
        if actions is None:
            actions = RunActions(
                reaction,
                self._artifactr,
                self._ledger,
                self.allowlist(reaction.run.rule),
                self._runner,
            )
            self._acting[reaction] = actions
        return actions


class RunActions:
    """What one attempt of a run does in artifactr. Get it with `Outbound.acting`."""

    def __init__(
        self,
        reaction: Reaction[Any],
        workspaces: artifactr.Workspaces,
        ledger: Ledger,
        allowlist: Allowlist,
        runner: artifactr.agent.Runner[Any] | None,
    ) -> None:
        self._reaction = reaction
        self._workspaces = workspaces
        self._ledger = ledger
        self._key = WorkspaceKey(reaction.workspace.tenant_id, reaction.workspace.workspace_id)
        self.allowlist = allowlist
        self._runner = runner
        self._workspace: artifactr.Workspace | None = None
        self._segment = reaction.run.checkpoints
        self._writes = 0
        self._threads = {
            envelope.event.thread_id
            for envelope in reaction.events
            if isinstance(envelope.event, ArtifactrEvent) and envelope.event.thread_id
        }

    @property
    def actor(self) -> a.ExternalAgentActor:
        """Who the run acts as in artifactr."""
        return rule_actor(self._reaction.run.rule)

    @property
    def threads(self) -> frozenset[str]:
        """The threads of the events that made the rule fire, and those the run created."""
        return frozenset(self._threads)

    # ─── what a run does ──────────────────────────────────────────────────────

    async def create(
        self,
        artifact: a.Artifact,
        *,
        thread_id: a.ThreadId | None = None,
        rationale: str | None = None,
    ) -> a.ArtifactId:
        """Create an artifact, by proposal unless the allowlist lets the rule create its kind.

        Returns:
            The artifact's id, derived from the run.
        """
        thread = self._where(thread_id)
        artifact_id, proposal_id = self._derive("art"), self._derive("prp")
        create = a.create_artifact(artifact, artifact_id=artifact_id, thread_id=thread)
        create = create.model_copy(update={"proposal_id": proposal_id})
        await self._caused(("proposal", proposal_id), ("artifact", artifact_id))
        await self._write(self._proposed(create, artifact.kind, proposal_id, rationale))
        return artifact_id

    async def edit(
        self,
        artifact_id: a.ArtifactId,
        path: str,
        value: JsonValue,
        *,
        summary: str | None = None,
        thread_id: a.ThreadId | None = None,
        rationale: str | None = None,
    ) -> None:
        """Set the value at a JSON Pointer `path` in an artifact: a keyed edit.

        It is a proposal unless the allowlist lets the rule edit the artifact's kind. It is
        skipped when the artifact already holds the value there, and re-read and made again,
        within the attempt, when the artifact changed meanwhile.

        Raises:
            RunFailure: If the artifact kept changing, so the attempt is retried.
        """
        thread = self._where(thread_id)
        proposal_id = self._derive("prp")
        patch = a.JsonPatch(ops=({"op": "add", "path": path, "value": value},))
        for _ in range(_TRIES):
            current = await self._read(artifact_id)
            data = current.data.to_json()
            if _holds(data, path, value):
                return
            edit = a.EditArtifact(
                artifact_id=artifact_id,
                base_version=current.version,
                patch=patch,
                summary=summary,
                thread_id=thread,
                proposal_id=proposal_id,
            )
            edited = f"{self.actor.client_id}/{artifact_id}@{current.version + 1}"
            await self._caused(("proposal", proposal_id), ("edit", edited))
            try:
                await self._write(self._proposed(edit, current.data.kind, proposal_id, rationale))
            except a.VersionConflict:
                continue
            return
        raise RunFailure(f"artifact {artifact_id} kept changing", reason="version_conflict")

    async def notice(self, content: str, *, thread_id: a.ThreadId | None = None) -> a.MessageId:
        """Post a notice: for people, starting and steering no turn.

        Args:
            content: What it says.
            thread_id: Where; by default the first thread of the events that made the rule fire.

        Returns:
            The notice's message id, derived from the run.
        """
        thread = self._thread(thread_id)
        message_id = self._derive("msg")
        notice = a.PostMessage(
            thread_id=thread, content=content, message_id=message_id, kind="notice"
        )
        await self._caused(("message", message_id))
        await self._write(notice)
        return message_id

    async def create_thread(self, title: str = "") -> a.ThreadId:
        """Create a thread, if the allowlist lets the rule, and act in it from then on.

        Returns:
            The thread's id, derived from the run.
        """
        if not self.allowlist.create_threads:
            raise NotAllowed(f"{self._rule} may not create threads")
        thread_id = self._derive("thr")
        await self._write(a.CreateThread(thread_id=thread_id, title=title))
        self._threads.add(thread_id)
        return thread_id

    async def send(self, content: str, *, thread_id: a.ThreadId | None = None) -> a.MessageId:
        """Send a message that starts the thread's next agent turn, if the allowlist lets it.

        Returns:
            The message's id, derived from the run.
        """
        runner = self._runner
        if not self.allowlist.turns or runner is None:
            raise NotAllowed(f"{self._rule} may not start turns; post a notice")
        thread = self._thread(thread_id)
        message_id = self._derive("msg")
        workspace = await self._open()
        await self._caused(("message", message_id))
        try:
            await runner.send(workspace, thread, content, message_id=message_id)
        except a.InvalidState:
            pass  # sent by an earlier attempt
        except a.Rejection as rejection:
            raise _permanent(rejection) from rejection
        return message_id

    async def read(self, artifact_id: a.ArtifactId) -> a.Versioned[a.Artifact]:
        """Return an artifact's current version, as the rule's actor reads it."""
        return await self._read(artifact_id)

    # ─── how ──────────────────────────────────────────────────────────────────

    @property
    def _rule(self) -> RuleName:
        return self._reaction.run.rule

    def _derive(self, prefix: str) -> str:
        """The id of the run's next write, the same on every attempt that makes it."""
        run = self._reaction.run
        if run.checkpoints != self._segment:
            self._segment, self._writes = run.checkpoints, 0
        seed = f"{run.id}\x00{self._segment}\x00{self._writes}"
        self._writes += 1
        return f"{prefix}_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"

    def _thread(self, thread_id: a.ThreadId | None) -> a.ThreadId:
        """The thread a message goes to: the one named, or the chain's first."""
        chosen = self._where(thread_id)
        if chosen is None:
            raise NotAllowed(f"{self._rule} has no thread to act in; name or create one")
        return chosen

    def _where(self, thread_id: a.ThreadId | None) -> a.ThreadId | None:
        """The thread a write is made from, if any: the one named, or the chain's first."""
        chosen = thread_id or min(self._threads, default=None)
        if chosen is not None and self.allowlist.threads == "chain" and chosen not in self._threads:
            raise NotAllowed(f"{self._rule} may act only in its chain's threads, not {chosen}")
        return chosen

    def _proposed(
        self,
        change: a.CreateArtifact | a.EditArtifact,
        kind: str,
        proposal_id: a.ProposalId,
        rationale: str | None,
    ) -> a.Command:
        if kind in self.allowlist.direct:
            return change
        return a.ProposeChange(proposal_id=proposal_id, change=change, rationale=rationale)

    async def _open(self) -> artifactr.Workspace:
        if self._workspace is None:
            self._workspace = await self._workspaces.open(*self._key, actor=self.actor)
        return self._workspace

    async def _read(self, artifact_id: a.ArtifactId) -> a.Versioned[a.Artifact]:
        workspace = await self._open()
        try:
            return await workspace.artifact(artifact_id)
        except a.Rejection as rejection:
            raise _permanent(rejection) from rejection

    async def _write(self, command: a.Command) -> None:
        """Commit a command; one an earlier attempt committed is done.

        Raises:
            VersionConflict: If an edit's artifact changed since it was read.
            RunFailure: If artifactr refuses it for good.
        """
        workspace = await self._open()
        try:
            await workspace.commit(command)
        except a.InvalidState:
            if isinstance(command, a.EditArtifact):
                raise RunFailure(
                    "the artifact can't be edited", reason="invalid_state", permanent=True
                ) from None
            return  # the derived id is used: an earlier attempt made it
        except a.VersionConflict:
            raise
        except a.Rejection as rejection:
            raise _permanent(rejection) from rejection

    async def _caused(self, *writes: tuple[CauseKind, str]) -> None:
        """Record the run behind writes it is about to make, by what the follower finds them by.

        Recorded before the write, so the follower never bridges a write it can't trace.
        """
        run = self._reaction.run
        causation = run.causation
        cause = Cause(
            correlation_id=run.correlation_id,
            firing_id=causation.firing_id,
            run_id=causation.run_id,
            depth=causation.depth,
        )
        for kind, key in writes:
            await self._ledger.record_cause(self._key, kind, key, cause)


def _holds(data: dict[str, JsonValue], path: str, value: JsonValue) -> bool:
    """Whether the data holds `value` at `path`."""
    test = a.JsonPatch(ops=({"op": "test", "path": path, "value": value},))
    try:
        a.apply_patch(data, test)
    except a.PatchFailed:
        return False
    return True


def _permanent(rejection: a.Rejection) -> RunFailure:
    return RunFailure(rejection.message, reason=rejection.code, permanent=True)
