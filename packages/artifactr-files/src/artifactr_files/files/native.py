"""Native files in a workspace: uploads, check-outs, check-ins, agents' edits and collection.

One writer at a time, through a lease on the artifact (artifactr ADR-0071): a person's
check-out holds it for hours, as `checkout:<id>:<participant>`, and an agent's edit for the
app's call and the commit, as `edit:<uuid>`. Every write puts its bytes first and then commits
one revision through the workspace, which a failure before the commit never reaches.
"""

import contextlib
import json
import uuid
from collections.abc import AsyncIterable, Sequence
from datetime import timedelta
from typing import Final, Literal

from pydantic import JsonValue

from artifactr.core import (
    Applied,
    ArtifactId,
    Forbidden,
    InvalidState,
    NotFound,
    ProposeChange,
    Proposed,
    ThreadId,
    ValidationFailed,
    VersionConflict,
    Versioned,
    create_artifact,
    new_artifact_id,
)
from artifactr.workspace import ArtifactBusy, Scope, Workspace
from artifactr_files.app import App, AppCommand, Inspection
from artifactr_files.blobs import Blobs, Clock, once
from artifactr_files.blobs.port import utc_now
from artifactr_files.checkouts import Checkout, Checkouts, holder_of
from artifactr_files.manifest import Blob, NativeFile, Provenance, revise

TEXT: Final = "text/plain; charset=utf-8"
JSON: Final = "application/json"

Part = Literal["content", "text", "review"]
"""What of a revision to read: the file, its words, or its comments and tracked changes."""


class ContentUnavailable(InvalidState):
    """A manifest names bytes the blob store doesn't have.

    Every surface can commit `edit_artifact`, so a hand-written patch can name a digest that was
    never put. Reads show the content as unavailable, and edits are refused until it is replaced.
    """

    def __init__(self, artifact_id: ArtifactId, part: Part) -> None:
        super().__init__(f"the {part} of artifact {artifact_id} is unavailable")
        self.artifact_id = artifact_id
        self.part: Part = part


class NativeFiles:
    """Native files in workspaces: their bytes, their check-outs and their app.

    Every method takes the [`Workspace`][artifactr.workspace.Workspace] to act in, as the actor
    who acts, and reads and writes through it, so `authorize` and the hiding of restricted
    artifacts apply as for any read or command.

    Args:
        blobs: Where the files' bytes are kept.
        checkouts: Where check-outs are kept.
        app: The app that reads the format and runs agents' commands.
        checkout_ttl: How long a check-out lasts, unless it is extended: eight hours by default.
        deadline: How long, in seconds, a call to the app may take: 30 by default.
        edit_ttl: How long an agent's edit holds the lease: the app's deadline and the commit,
            45 seconds by default. It is never renewed: an edit that outlives it is still refused
            at commit, by its base version and its test, if someone else committed meanwhile.
        keep: How long bytes no revision names are kept after they were last put, for the
            commit that follows a put: a day by default.
        clock: Returns the current time, which collection keeps bytes from.

    Raises:
        ValueError: If an edit's lease would end before the app's deadline.
    """

    def __init__(
        self,
        blobs: Blobs,
        checkouts: Checkouts,
        app: App,
        *,
        checkout_ttl: timedelta = timedelta(hours=8),
        deadline: float = 30.0,
        edit_ttl: timedelta = timedelta(seconds=45),
        keep: timedelta = timedelta(days=1),
        clock: Clock = utc_now,
    ) -> None:
        if edit_ttl.total_seconds() <= deadline:
            raise ValueError("an edit's lease must outlast the app's deadline, and the commit")
        self._blobs = blobs
        self._checkouts = checkouts
        self._app = app
        self._checkout_ttl = checkout_ttl
        self._deadline = deadline
        self._edit_ttl = edit_ttl
        self._keep = keep
        self._clock = clock

    # ─── uploads ──────────────────────────────────────────────────────────────

    async def upload[F: NativeFile](
        self,
        ws: Workspace,
        file_type: type[F],
        name: str,
        data: AsyncIterable[bytes],
        *,
        media_type: str,
        artifact_id: ArtifactId | None = None,
        thread_id: ThreadId | None = None,
    ) -> Applied | Proposed:
        """Create a native file from uploaded bytes, with a new id unless one is given.

        Raises:
            ValidationFailed: If the type doesn't hold files of `media_type`.
            TooLarge: If the file is larger than the blob store's limit.
            AppFailed: If the app can't read it.
        """
        if media_type not in file_type.formats:
            raise ValidationFailed(f"a {file_type.kind} holds {sorted(file_type.formats)}", [])
        artifact_id = artifact_id or new_artifact_id()
        scope = _scope(ws)
        content = await self._blobs.put(scope, artifact_id, data, media_type)
        inspection = await self._inspect(scope, artifact_id, content)
        made = Provenance(source="upload")
        manifest = await self._manifest(
            scope, artifact_id, file_type, name, content, inspection, made
        )
        return await ws.commit(
            create_artifact(manifest, artifact_id=artifact_id, thread_id=thread_id)
        )

    # ─── check-out and check-in ───────────────────────────────────────────────

    async def check_out(self, ws: Workspace, artifact_id: ArtifactId) -> Checkout:
        """Check a native file out to the workspace's actor, holding its lease.

        The lease is taken before the head is read, so the version checked out is the one the
        lease holds the file at.

        Raises:
            ArtifactBusy: If someone else has the file: a check-out, or an agent's edit.
            NotFound: If there is no such native file, or it is hidden from the actor.
        """
        checkout_id = f"co_{uuid.uuid4().hex}"
        holder = holder_of(checkout_id, ws.actor)
        try:
            lease = await ws.lease_artifact(artifact_id, holder=holder, ttl=self._checkout_ttl)
            head = await ws.get(NativeFile, artifact_id)
            checkout = Checkout(
                id=checkout_id,
                artifact_id=artifact_id,
                base_version=head.version,
                base_sha256=head.data.content.sha256,
                actor=ws.actor,
                expires_at=lease.expires_at,
            )
            await self._checkouts.save(_scope(ws), checkout)
        except BaseException:
            # The holder is new, so whatever it holds is this call's alone. A release that fails
            # too leaves the lease to lapse; the caller hears the first error.
            with contextlib.suppress(Exception):
                await ws.release_artifact(artifact_id, holder=holder)
            raise
        return checkout

    async def extend(self, ws: Workspace, checkout_id: str) -> Checkout:
        """Extend a check-out by its whole length again, from now.

        Raises:
            NotFound: If there is no such check-out.
            Forbidden: If it is someone else's.
            ArtifactBusy: If its lease ended and someone else has the file now.
            InvalidState: If it was checked in.
        """
        checkout = await self._own(ws, checkout_id)
        if checkout.checked_in:
            raise InvalidState(f"checkout {checkout_id} was checked in: check the file out again")
        lease = await ws.lease_artifact(
            checkout.artifact_id, holder=checkout.holder, ttl=self._checkout_ttl
        )
        extended = checkout.model_copy(update={"expires_at": lease.expires_at})
        await self._checkouts.save(_scope(ws), extended)
        return extended

    async def check_in(
        self,
        ws: Workspace,
        checkout_id: str,
        data: AsyncIterable[bytes],
        *,
        summary: str | None = None,
    ) -> Applied | Proposed | None:
        """Check a file in: a revision from the version checked out, and the lease released.

        The base is the check-out's, never the upload's. The lease is taken again first, which
        renews one that lapsed if no one else took it. A file whose fingerprint is the head's
        commits nothing, so a check-in retried after it succeeded does nothing. A check-in that
        is stale, because its lease lapsed and someone else took the file or committed
        meanwhile, is kept as a proposal against the head, which tests the head's digest and
        records the check-out's base as its provenance. Either way the check-out ends: its
        record is closed and its lease released.

        Returns:
            The revision's outcome, a proposal's if it was stale, or None if nothing changed.

        Raises:
            NotFound: If there is no such check-out, or its file is hidden from the actor.
            Forbidden: If it is someone else's.
            InvalidState: If it was checked in already, and this file is another.
            TooLarge: If the file is larger than the blob store's limit.
            AppFailed: If the app can't read it.
        """
        checkout = await self._own(ws, checkout_id)
        artifact_id = checkout.artifact_id
        head = await ws.get(NativeFile, artifact_id)
        scope = _scope(ws)
        content = await self._blobs.put(scope, artifact_id, data, head.data.content.media_type)
        inspection = await self._inspect(scope, artifact_id, content)
        if inspection.fingerprint == head.data.fingerprint:
            await self._close(ws, checkout)
            return None
        if checkout.checked_in:
            raise InvalidState(f"checkout {checkout_id} was checked in: check the file out again")
        made = Provenance(source="check_in", base=checkout.base_sha256)
        after = await self._manifest(
            scope, artifact_id, type(head.data), head.data.name, content, inspection, made
        )
        summary = summary or f"Checked in {head.data.name}"
        edit = revise(
            artifact_id,
            after,
            base_version=checkout.base_version,
            tested=checkout.base_sha256,
            summary=summary,
        )
        try:
            await ws.lease_artifact(artifact_id, holder=checkout.holder, ttl=self._checkout_ttl)
            outcome = await ws.commit(edit)
        except (ArtifactBusy, VersionConflict):
            outcome = await self._stale(ws, checkout, after, summary)
        await self._close(ws, checkout)
        return outcome

    async def _close(self, ws: Workspace, checkout: Checkout) -> None:
        """End a check-out: its record is closed, and its lease released."""
        if not checkout.checked_in:
            closed = checkout.model_copy(update={"checked_in": True})
            await self._checkouts.save(_scope(ws), closed)
        await ws.release_artifact(checkout.artifact_id, holder=checkout.holder)

    async def _stale(
        self, ws: Workspace, checkout: Checkout, after: NativeFile, summary: str
    ) -> Proposed | None:
        """Keep a stale check-in as a proposal against the head, unless the head has it."""
        head = await ws.get(NativeFile, checkout.artifact_id)
        if head.data.fingerprint == after.fingerprint:
            return None
        change = revise(
            checkout.artifact_id,
            after,
            base_version=head.version,
            tested=head.data.content.sha256,
            summary=summary,
        )
        rationale = (
            f"Checked in from version {checkout.base_version}, after the check-out's lease "
            f"lapsed, when the file was at version {head.version}"
        )
        return await ws.commit(ProposeChange(change=change, rationale=rationale))

    async def _own(self, ws: Workspace, checkout_id: str) -> Checkout:
        checkout = await self._checkouts.get(_scope(ws), checkout_id)
        if checkout is None:
            raise NotFound("checkout", checkout_id)
        if checkout.actor.participant != ws.actor.participant:
            raise Forbidden(f"checkout {checkout_id} is someone else's")
        return checkout

    # ─── agents' edits ────────────────────────────────────────────────────────

    async def edit(
        self,
        ws: Workspace,
        artifact_id: ArtifactId,
        *,
        base_version: int,
        commands: Sequence[AppCommand],
        summary: str,
        thread_id: ThreadId | None = None,
    ) -> Applied | Proposed | None:
        """Edit a native file by a batch of its app's commands, holding its lease meanwhile.

        For an agent, under the type's `propose` write policy, the revision is a proposal.

        Returns:
            The revision's outcome, or None if the batch changed nothing.

        Raises:
            NotFound: If there is no such native file, or it is hidden from the actor.
            VersionConflict: If `base_version` isn't the head's: the agent plans again.
            ArtifactBusy: If someone else has the file, such as a person's check-out. The agent
                plans again after the check-in, or at once if the busy lease is None.
            ContentUnavailable: If the head's bytes aren't in the blob store.
            AppFailed: If the app can't run the batch.
        """
        holder = f"edit:{uuid.uuid4()}"
        try:
            await ws.lease_artifact(artifact_id, holder=holder, ttl=self._edit_ttl)
            head = await ws.get(NativeFile, artifact_id)
            if head.version != base_version:
                raise VersionConflict(artifact_id, base=base_version, head=head.version)
            scope = _scope(ws)
            source = await self._bytes(scope, artifact_id, head.data.content, "content")
            applied = await self._app.apply(source, commands, deadline=self._deadline)
            if applied.inspection.fingerprint == head.data.fingerprint:
                return None
            batch: list[JsonValue] = [command.model_dump(mode="json") for command in commands]
            made = Provenance(
                source="commands",
                app=self._app.name,
                app_version=self._app.version,
                build=self._app.build,
                base=head.data.content.sha256,
                commands=await self._put_json(scope, artifact_id, batch),
            )
            media_type = head.data.content.media_type
            content = await self._blobs.put(scope, artifact_id, once(applied.content), media_type)
            after = await self._manifest(
                scope,
                artifact_id,
                type(head.data),
                head.data.name,
                content,
                applied.inspection,
                made,
            )
            edit = revise(
                artifact_id,
                after,
                base_version=head.version,
                tested=head.data.content.sha256,
                summary=summary,
                thread_id=thread_id,
            )
            return await ws.commit(edit)
        finally:
            # The holder is unique to this call, so whatever it took is released, even if the call
            # was cut short. A release that fails leaves the lease to lapse, in seconds.
            with contextlib.suppress(Exception):
                await ws.release_artifact(artifact_id, holder=holder)

    # ─── reads ────────────────────────────────────────────────────────────────

    async def read(
        self,
        ws: Workspace,
        artifact_id: ArtifactId,
        *,
        version: int | None = None,
        part: Part = "content",
    ) -> bytes:
        """Return a native file's bytes, its text or its review, at its head or a version.

        The artifact is resolved through the workspace first, which asks `authorize` and hides
        restricted artifacts, and only then are the bytes its revision names read.

        Raises:
            NotFound: If there is no such native file or version, or the file is hidden.
            ContentUnavailable: If the revision names nothing for `part`, or bytes the blob
                store doesn't have.
        """
        head = await ws.get(NativeFile, artifact_id)
        manifest = head.data if version in (None, head.version) else await _at(ws, head, version)
        parts = {"content": manifest.content, "text": manifest.text, "review": manifest.review}
        return await self._bytes(_scope(ws), artifact_id, parts[part], part)

    # ─── collection ───────────────────────────────────────────────────────────

    async def collect(self, ws: Workspace) -> int:
        """Delete the workspace's blobs that nothing names, unless they were put lately.

        Named means by a pending proposal, or by any revision of a native file, archived ones
        too; the proposals are read first, so that one accepted meanwhile is read as a
        revision. Bytes put within `keep` are kept whatever names them, for the commit that
        follows a put. The handle must see every thread and artifact, as an application's own
        actor does: a blob that only a hidden revision names would otherwise be lost.

        Returns:
            How many blobs were deleted.

        Raises:
            Forbidden: If the handle's actor can't see everything in the workspace.
        """
        hidden = await ws.hidden()
        if hidden.threads or hidden.artifacts:
            raise Forbidden("collecting blobs needs a handle that sees the whole workspace")
        before = self._clock() - self._keep
        referenced: set[tuple[ArtifactId, str]] = set()
        for proposal in await ws.proposals(status="pending"):
            named = digests(proposal.change.model_dump(mode="json"))
            referenced |= {(proposal.artifact_id, sha256) for sha256 in named}
        for artifact in await ws.artifacts(NativeFile, include_archived=True):
            for revision in await ws.revisions(artifact.id):
                referenced |= {(artifact.id, sha256) for sha256 in digests(revision.data)}
        return await self._blobs.collect(_scope(ws), referenced, before=before)

    # ─── what every write shares ──────────────────────────────────────────────

    async def _inspect(self, scope: Scope, artifact_id: ArtifactId, content: Blob) -> Inspection:
        source = await self._bytes(scope, artifact_id, content, "content")
        return await self._app.inspect(source, deadline=self._deadline)

    async def _manifest[F: NativeFile](
        self,
        scope: Scope,
        artifact_id: ArtifactId,
        file_type: type[F],
        name: str,
        content: Blob,
        inspection: Inspection,
        provenance: Provenance,
    ) -> F:
        """Put the text and the review the app read, and make the manifest that names them."""
        text = await self._blobs.put(scope, artifact_id, once(inspection.text.encode()), TEXT)
        return file_type(
            name=name,
            content=content,
            fingerprint=inspection.fingerprint,
            text=text,
            review=await self._put_json(scope, artifact_id, inspection.review),
            outline=inspection.outline,
            pages=inspection.pages,
            provenance=provenance,
        )

    async def _put_json(self, scope: Scope, artifact_id: ArtifactId, value: JsonValue) -> Blob:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return await self._blobs.put(scope, artifact_id, once(canonical.encode()), JSON)

    async def _bytes(
        self, scope: Scope, artifact_id: ArtifactId, blob: Blob | None, part: Part
    ) -> bytes:
        found = None if blob is None else await self._blobs.get(scope, artifact_id, blob.sha256)
        if found is None:
            raise ContentUnavailable(artifact_id, part)
        return found


def digests(value: JsonValue) -> set[str]:
    """Every blob's digest a manifest, or a patch or a command holding one, names."""
    match value:
        case {"sha256": str(sha256), "size": int(), "media_type": str(), **rest}:
            return {sha256} | {d for v in rest.values() for d in digests(v)}
        case dict():
            return {d for v in value.values() for d in digests(v)}
        case list():
            return {d for v in value for d in digests(v)}
        case _:
            return set()


def _scope(ws: Workspace) -> Scope:
    return Scope(ws.tenant_id, ws.workspace_id)


async def _at(ws: Workspace, head: Versioned[NativeFile], version: int) -> NativeFile:
    """A native file's manifest at one of its versions."""
    for revision in await ws.revisions(head.id):
        if revision.version == version:
            return type(head.data).model_validate(revision.data)
    raise NotFound("revision", f"{head.id}@{version}")
