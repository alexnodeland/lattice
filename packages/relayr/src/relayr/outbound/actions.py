"""The outbound adapter: a run of a rule acts in artifactr, as the rule's own participant.

[`Outbound.acting`][relayr.outbound.Outbound.acting] gives a run its
[`RunActions`][relayr.outbound.RunActions]: create an artifact, make a keyed edit, post a notice,
create a thread, and, if the rule's allowlist grants it, send a message that starts a turn.
Each acts as `ExternalAgentActor(client_id="reflexr:<rule>")`, so artifactr's own rules apply to
it, and none can resolve a proposal.

Every write's ids are derived from the run and what the write is: the artifact and path it
edits, the kind and data it creates, the thread and text it posts, the title of the thread it
creates. A retried attempt that makes the same writes, in any order, makes them with the same ids,
and artifactr refuses each again: a proposal, an artifact, a thread and a message are each made
once. An edit sets one value at one path, and is skipped when the value is in place. Before each
write, the ledger records the run behind it, by the ids the follower finds it by, so the follower
continues the run's causal chain when it bridges the write back into reflexr.
"""

import hashlib
import json
import re
import weakref
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final

from pydantic import JsonValue

import artifactr
import artifactr.agent
import artifactr.core as a
from reflexr.core import RuleName
from reflexr.workspace import Reaction, RunFailure
from relayr.events import ArtifactrEvent
from relayr.ledger import Cause, CauseKind, Ledger, WorkspaceKey
from relayr.outbound.allowlist import Allowlist

RULES: Final = "reflexr:"
"""The prefix of a rule's actor's `client_id` in artifactr: `reflexr:<rule>`."""

_TRIES = 3
"""How many times an edit re-reads its artifact after a version conflict, within an attempt."""

type _Done = Callable[[artifactr.Workspace], Awaitable[bool]]
"""Whether a write's derived id is used: an earlier attempt made it."""


class NotAllowed(RunFailure):
    """The rule's allowlist doesn't allow what its run tried. Permanent: a retry would try again."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason="not_allowed", permanent=True)


class Refused(RunFailure):
    """artifactr refused a write as invalid, or about something missing.

    An agent's tools hand it back to the model, which can do otherwise; from a function action,
    it fails the attempt, which is retried. Its reason is artifactr's code: `validation_failed`,
    `patch_failed` or `not_found`.
    """

    def __init__(self, rejection: a.Rejection) -> None:
        super().__init__(rejection.message, reason=rejection.code)


def rule_actor(rule: RuleName) -> a.ExternalAgentActor:
    """Who a rule's runs act as in artifactr: an external agent of their own, for no person."""
    return a.ExternalAgentActor(client_id=f"{RULES}{rule}", name=rule)


def is_rule_actor(actor: a.Actor) -> bool:
    """Whether an artifactr actor is a rule's: the actor a rule's runs act as, for no person."""
    return (
        isinstance(actor, a.ExternalAgentActor)
        and actor.client_id.startswith(RULES)
        and actor.on_behalf_of is None
    )


class Outbound:
    """Lets the runs of rules act in artifactr, each within its rule's allowlist.

    Give it to the actions that act in artifactr, as their dependency or through
    [`ArtifactrCapability`][relayr.outbound.ArtifactrCapability].

    Args:
        artifactr: The workspaces runs act in: the same tenant and id as the run's.
        ledger: Where the run behind each write is recorded, for the follower.
        allowlists: Each rule's allowlist, by name, or by a whole namespace's, as ``"chat:*"``,
            for rules installed at runtime. A rule's own name comes first; a rule with neither
            gets the default.
        runner: Starts the turns that rules allowed to `send` ask for. Without one, no rule may.

    Raises:
        ValueError: If a key of ``allowlists`` has a wildcard other than a whole namespace's.
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
        if wild := sorted(k for k in self._allowlists if "*" in k and not _NAMESPACE.fullmatch(k)):
            raise ValueError(f"only a whole namespace may be a wildcard, as 'chat:*': {wild}")
        self._runner = runner
        self._acting: weakref.WeakKeyDictionary[Reaction[Any], RunActions] = (
            weakref.WeakKeyDictionary()
        )

    def acting(self, reaction: Reaction[Any]) -> "RunActions":
        """Return what an attempt of a run may do in artifactr; the same for the whole attempt."""
        actions = self._acting.get(reaction)
        if actions is None:
            rule = reaction.run.rule
            namespace = f"{rule.partition(':')[0]}:*"
            allowlist = self._allowlists.get(rule) or self._allowlists.get(namespace, Allowlist())
            actions = RunActions(reaction, self._artifactr, self._ledger, allowlist, self._runner)
            self._acting[reaction] = actions
        return actions


class RunActions:
    """What one attempt of a run does in artifactr. Get it with `Outbound.acting`.

    A write without a thread goes to the chain's first thread: that of the first event that made
    the rule fire with one, or else the first the run created.
    """

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
        self._allowlist = allowlist
        self._runner = runner
        self._actor = rule_actor(reaction.run.rule)
        self._workspace: artifactr.Workspace | None = None
        self._made: Counter[tuple[int, str, str]] = Counter()
        self._threads = dict.fromkeys(
            envelope.event.thread_id
            for envelope in reaction.events
            if isinstance(envelope.event, ArtifactrEvent) and envelope.event.thread_id
        )

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
            The artifact's id, derived from the run, the kind and the data.

        Raises:
            Refused: If artifactr finds the artifact invalid.
        """
        thread = self._where(thread_id)
        made = self._derive("create", artifact.kind, _canonical(artifact.to_json()))
        artifact_id, proposal_id = f"art_{made}", f"prp_{made}"
        create = a.create_artifact(artifact, artifact_id=artifact_id, thread_id=thread)
        create = create.model_copy(update={"proposal_id": proposal_id})

        async def done(workspace: artifactr.Workspace) -> bool:
            return await _exists(workspace.proposal(proposal_id)) or await _exists(
                workspace.artifact(artifact_id)
            )

        await self._caused(("proposal", proposal_id), ("artifact", artifact_id))
        await self._write(self._proposed(create, artifact.kind, proposal_id, rationale), done)
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
        within the attempt, when the artifact changed meanwhile. A direct edit retried after
        someone else changed the value sets the run's value again: a direct change carries no id
        to tell an earlier attempt's from another's.

        Raises:
            RunFailure: If the artifact kept changing, so the attempt is retried; or, for good,
                if it is archived.
            Refused: If the artifact is missing, or the patch doesn't apply.
        """
        thread = self._where(thread_id)
        proposal_id = f"prp_{self._derive('edit', artifact_id, path)}"
        patch = a.JsonPatch(ops=({"op": "add", "path": path, "value": value},))

        async def done(workspace: artifactr.Workspace) -> bool:
            return await _exists(workspace.proposal(proposal_id))

        for _ in range(_TRIES):
            current = await self._read(artifact_id)
            if current.archived:
                raise RunFailure(
                    f"artifact {artifact_id} is archived", reason="invalid_state", permanent=True
                )
            if _holds(current.data.to_json(), path, value):
                return
            edit = a.EditArtifact(
                artifact_id=artifact_id,
                base_version=current.version,
                patch=patch,
                summary=summary,
                thread_id=thread,
                proposal_id=proposal_id,
            )
            edited = f"{self._actor.client_id}/{artifact_id}@{current.version + 1}"
            await self._caused(("proposal", proposal_id), ("edit", edited))
            command = self._proposed(edit, current.data.kind, proposal_id, rationale)
            try:
                await self._write(command, done)
            except a.VersionConflict:
                continue
            return
        raise RunFailure(f"artifact {artifact_id} kept changing", reason="version_conflict")

    async def notice(self, content: str, *, thread_id: a.ThreadId | None = None) -> a.MessageId:
        """Post a notice: for people, starting and steering no turn.

        Args:
            content: What it says.
            thread_id: Where; by default the chain's first thread.

        Returns:
            The notice's message id, derived from the run, the thread and the text.
        """
        thread = self._thread(thread_id)
        message_id = f"msg_{self._derive('notice', thread, _canonical(content))}"
        notice = a.PostMessage(
            thread_id=thread, content=content, message_id=message_id, kind="notice"
        )
        await self._caused(("message", message_id))
        await self._write(notice, _used)
        return message_id

    async def create_thread(self, title: str = "") -> a.ThreadId:
        """Create a thread, if the allowlist lets the rule, and act in it from then on.

        Returns:
            The thread's id, derived from the run and the title.
        """
        if not self._allowlist.create_threads:
            raise NotAllowed(f"{self._rule} may not create threads")
        thread_id = f"thr_{self._derive('thread', title)}"

        await self._write(a.CreateThread(thread_id=thread_id, title=title), _used)
        self._threads[thread_id] = None
        return thread_id

    async def send(self, content: str, *, thread_id: a.ThreadId | None = None) -> a.MessageId:
        """Send a message that starts the thread's next agent turn, if the allowlist lets it.

        Returns:
            The message's id, derived from the run, the thread and the text.
        """
        runner = self._runner
        if not self._allowlist.turns or runner is None:
            raise NotAllowed(f"{self._rule} may not start turns; post a notice")
        thread = self._thread(thread_id)
        message_id = f"msg_{self._derive('send', thread, _canonical(content))}"
        workspace = await self._open()
        await self._caused(("message", message_id))
        try:
            try:
                await runner.send(workspace, thread, content, message_id=message_id)
            except a.InvalidState:
                # The message id is used (see `_used`): an earlier attempt sent it, and may have
                # stopped before it asked for the turn. Asking starts the turn, or does nothing.
                await runner.ask(workspace, thread)
        except a.Rejection as rejection:
            raise _refused(rejection) from rejection
        return message_id

    async def read(self, artifact_id: a.ArtifactId) -> a.Versioned[a.Artifact]:
        """Return an artifact's current version, as the rule's actor reads it.

        Raises:
            Refused: If there is no such artifact.
        """
        return await self._read(artifact_id)

    # ─── how ──────────────────────────────────────────────────────────────────

    @property
    def _rule(self) -> RuleName:
        return self._reaction.run.rule

    def _derive(self, op: str, *key: str) -> str:
        """The digest a write's ids are made from, the same on every attempt that makes it.

        It is made of the run, its segment, what the write is, and how many such writes the
        attempt made before it.
        """
        run = self._reaction.run
        what = "\x00".join(key)
        made = (run.checkpoints, op, what)
        seed = f"{run.id}\x00{run.checkpoints}\x00{op}\x00{what}\x00{self._made[made]}"
        self._made[made] += 1
        return hashlib.sha256(seed.encode()).hexdigest()[:16]

    def _thread(self, thread_id: a.ThreadId | None) -> a.ThreadId:
        """The thread a message goes to: the one named, or the chain's first."""
        chosen = self._where(thread_id)
        if chosen is None:
            raise NotAllowed(f"{self._rule} has no thread to act in; name or create one")
        return chosen

    def _where(self, thread_id: a.ThreadId | None) -> a.ThreadId | None:
        """The thread a write is made from, if any: the one named, or the chain's first."""
        chosen = thread_id or next(iter(self._threads), None)
        in_chain = chosen is None or chosen in self._threads
        if not in_chain and self._allowlist.threads == "chain":
            raise NotAllowed(f"{self._rule} may act only in its chain's threads, not {chosen}")
        return chosen

    def _proposed(
        self,
        change: a.CreateArtifact | a.EditArtifact,
        kind: str,
        proposal_id: a.ProposalId,
        rationale: str | None,
    ) -> a.Command:
        if kind in self._allowlist.direct:
            return change
        return a.ProposeChange(proposal_id=proposal_id, change=change, rationale=rationale)

    async def _open(self) -> artifactr.Workspace:
        if self._workspace is None:
            self._workspace = await self._workspaces.open(*self._key, actor=self._actor)
        return self._workspace

    async def _read(self, artifact_id: a.ArtifactId) -> a.Versioned[a.Artifact]:
        workspace = await self._open()
        try:
            return await workspace.artifact(artifact_id)
        except a.Rejection as rejection:
            raise _refused(rejection) from rejection

    async def _write(self, command: a.Command, done: _Done) -> None:
        """Commit a command; one whose derived id an earlier attempt used is done.

        Raises:
            VersionConflict: If an edit's artifact changed since it was read.
            RunFailure: If artifactr refuses it.
        """
        workspace = await self._open()
        try:
            await workspace.commit(command)
        except a.InvalidState as invalid:
            if not await done(workspace):
                raise _refused(invalid) from invalid
        except a.VersionConflict:
            raise
        except a.Rejection as rejection:
            raise _refused(rejection) from rejection

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


def _canonical(value: JsonValue) -> str:
    """A digest of JSON data, the same for equal data."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


async def _exists(read: Awaitable[object]) -> bool:
    try:
        await read
    except a.NotFound:
        return False
    return True


async def _used(_: artifactr.Workspace) -> bool:
    """Done, for a message or a thread, whose only `InvalidState` is a used id.

    artifactr refuses a message or a thread so only when its id is used (artifactr ADR-0045), and
    its id is derived from the run and what it says, so an earlier attempt used it.
    """
    return True


_NAMESPACE: Final = re.compile(r"[a-z][a-z0-9_]*:\*")
"""An allowlist's key for a whole rule namespace, as reflexr names namespaces."""

_RETRIED: Final = frozenset({"validation_failed", "patch_failed", "not_found"})
"""The refusals a run can do otherwise about: an agent's model is told, and may retry."""


def _refused(rejection: a.Rejection) -> RunFailure:
    if rejection.code in _RETRIED:
        return Refused(rejection)
    return RunFailure(rejection.message, reason=rejection.code, permanent=True)
