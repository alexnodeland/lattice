"""Native files in a workspace: uploads, blank files, check-outs, check-ins, edits, collection.

One writer at a time, through a lease on the artifact (artifactr ADR-0071): a person's
check-out holds it for hours, as `checkout:<id>:<participant>`, and an agent's edit for the
app's call and the commit, as `edit:<uuid>`. Every write puts its bytes first and then commits
one revision through the workspace, which a failure before the commit never reaches.
"""

import asyncio
import contextlib
import hashlib
import json
import time
import uuid
from collections import Counter, OrderedDict
from collections.abc import (
    AsyncGenerator,
    AsyncIterable,
    Awaitable,
    Callable,
    Generator,
    Mapping,
    Sequence,
)
from datetime import timedelta
from typing import Final, Literal, cast, override

from pydantic import JsonValue, TypeAdapter, ValidationError

from artifactr.core import (
    AgentActor,
    AlreadyExists,
    Applied,
    Artifact,
    ArtifactId,
    EditArtifact,
    Forbidden,
    InvalidState,
    JsonPatch,
    NotEnabled,
    NotFound,
    Patch,
    ProposalId,
    ProposeChange,
    Proposed,
    ThreadId,
    ValidationFailed,
    VersionConflict,
    Versioned,
    artifact_types,
    create_artifact,
    new_artifact_id,
)
from artifactr.files.app import App, AppCommand, AppFailed, Inspection
from artifactr.files.blobs import Blobs, Clock, once
from artifactr.files.blobs.port import TooLarge, spool, utc_now
from artifactr.files.checkouts import Checkout, Checkouts, holder_of
from artifactr.files.manifest import Blob, NativeFile, Provenance, revise
from artifactr.files.native.describe import ProposalDescription, describe
from artifactr.files.native.formats import FORMATS, Format, file_name, sniffed
from artifactr.files.native.pace import Gauge, Pace
from artifactr.workspace import Access, ArtifactBusy, Scope, Workspace
from lattice_core.integrations import Integrations

TEXT: Final = "text/plain; charset=utf-8"
JSON: Final = "application/json"

CREATE_NATIVE_FILE: Final = "artifactr:create_native_file"
"""The action a person's upload over HTTP asks `authorize` before any of its bytes are read:
an editor's, as `artifactr:create_artifact` is, which its commit asks too."""

CREATE_ARTIFACT: Final = "artifactr:create_artifact"
"""The action `create` asks of an agent as well, before its commit asks it of the person."""

Part = Literal["content", "text", "review"]
"""What of a revision to read: the file, its words, or its comments and tracked changes."""

_COMMANDS: Final = TypeAdapter(list[AppCommand])

BATCH_MOST: Final = 4 << 20
"""The most bytes of a proposal's batch that are read to say what it does: past it, none is."""


class ContentUnavailable(InvalidState):
    """A manifest names bytes the blob store doesn't have.

    Every surface can commit `edit_artifact`, so a hand-written patch can name a digest that was
    never put. Reads show the content as unavailable, and edits are refused until it is replaced.
    """

    def __init__(self, artifact_id: ArtifactId, part: Part | Literal["commands"]) -> None:
        super().__init__(f"the {part} of artifact {artifact_id} is unavailable")
        self.artifact_id = artifact_id
        self.part: Part | Literal["commands"] = part


class FormatChanged(InvalidState):
    """A check-in is in another format than the file checked out, which is never converted.

    An editor can save a file in another format than it opened, such as a workbook opened from
    `.csv` saved as `.xlsx`, or a layout opened from INDD saved as IDML. The head keeps its
    format: check the file in as a new one instead (native files ADR-0012).
    """

    def __init__(self, artifact_id: ArtifactId, *, checked_out: str, checked_in: str) -> None:
        super().__init__(
            f"artifact {artifact_id} is {checked_out}, and the file checked in is {checked_in}: "
            "a format is never changed by a check-in, so upload it as a new file"
        )
        self.artifact_id = artifact_id
        self.checked_out = checked_out
        self.checked_in = checked_in

    @override
    def details(self) -> dict[str, JsonValue]:
        """Return the format checked out and the one checked in."""
        return {"checked_out": self.checked_out, "checked_in": self.checked_in}


type PageKey = tuple[str, str, ArtifactId, str, str, int, float]
"""A kept page's key: the tenant, the workspace, the file, its app, the blob's digest, the page
and the scale."""


LOOK_AGAIN: Final = 0.05
"""How often, in seconds, a page waiting for one of its tenant's readings looks again."""


class Busy(Exception):
    """The tenant has as many files being read as it may at once; nothing was read or committed.

    The worker runs one job at a time, so one person's uploads would otherwise queue everyone's.

    Attributes:
        limit: How many files a tenant may have read at once.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(f"{limit} of the tenant's files are being read: try again shortly")
        self.limit = limit


class Paced(Exception):
    """Too many files are being made: by the actor this minute, or by this process now.

    Nothing was read or committed.

    Attributes:
        wait: The seconds until the actor's pace lets another through; None if every place is
            held, which frees when some file is done.
    """

    def __init__(self, wait: int | None) -> None:
        when = "shortly" if wait is None else f"in {wait} seconds"
        super().__init__(f"too many files are being made: try again {when}")
        self.wait = wait


class NativeFiles:
    """Native files in workspaces: their bytes, their check-outs and the apps that read them.

    Every method takes the [`Workspace`][artifactr.workspace.Workspace] to act in, as the actor
    who acts, and reads and writes through it, so `authorize` and the hiding of restricted
    artifacts apply as for any read or command.

    Args:
        blobs: Where the files' bytes are kept.
        checkouts: Where check-outs are kept.
        app: The app that reads every native file and runs agents' commands on it; or, for
            several, the app for each native type, a subclass's own or else its nearest base's.
        checkout_ttl: How long a check-out lasts, unless it is extended: eight hours by default.
        deadline: How long, in seconds, a call to the app may take: 30 by default.
        edit_ttl: How long an agent's edit holds the lease: the app's deadline and the commit,
            45 seconds by default. It is never renewed: an edit that outlives it is still refused
            at commit, by its base version and its test, if someone else committed meanwhile.
        keep: How long bytes no revision names are kept after they were last put, for the
            commit that follows a put: a day by default.
        clock: Returns the current time, which collection keeps bytes from.
        integrations: Whether a file's app's integration, `app.integration`, is on in a
            workspace: while it is off there, none of its files is uploaded, checked out,
            extended, checked in or edited, and each refuses with `NotEnabled`; reads and
            collection go on. None, the default, is on everywhere.
        formats: Each format an upload's first bytes are told by, by media type: lattice's
            native types' by default. An application with a native type of its own adds its
            format's.
        readings: How many files each tenant may have the app read or render at once, uploaded,
            checked in or a page of one, past which another is refused with `Busy`: two by
            default, None for no limit. It is this process's count, so each replica of an
            application counts its own. The app's worker does one call at a time, so this is
            what keeps one tenant's calls from filling its queue for every other's. A page
            waits up to `deadline` for a reading, since a viewer asks for a few at once.
        pages: How many bytes of rendered pages this process keeps, by the bytes they are of,
            the page and the scale, so a page asked for again doesn't reach the app: 64 MiB by
            default, 0 for none. A page is the same for any reader of the same bytes, and only
            a reader the workspace lets read them is given it.
        waiting: How many of a tenant's pages may wait for one of its readings at once, past
            which another is refused with `Busy` at once: eight by default, twice the pages a
            viewer's first screen asks for.
        naming: Other artifact types whose revisions name bytes in the same store, such as
            diagrams, whose images it keeps: collection keeps what their revisions and their
            pending proposals name too (artifactr ADR-0090).
        pace: How many files each of a tenant's people may start in a minute, in this process,
            past which `create` refuses another with `Paced`; None, the default, for no pace.
            `files_router` paces uploads by it too, in place of its own.
        gauge: How many files this process makes at once, a tenant's and a person's share,
            past which `create` refuses another with `Paced`; None, the default, for no limit.
            `files_router` holds uploads and check-ins to it too, in place of its own.

    Raises:
        ValueError: If an edit's lease would end before the apps' deadline, or no app is given.
    """

    def __init__(
        self,
        blobs: Blobs,
        checkouts: Checkouts,
        app: App | Mapping[type[NativeFile], App],
        *,
        checkout_ttl: timedelta = timedelta(hours=8),
        deadline: float = 30.0,
        edit_ttl: timedelta = timedelta(seconds=45),
        keep: timedelta = timedelta(days=1),
        clock: Clock = utc_now,
        integrations: Integrations | None = None,
        formats: Mapping[str, Format] = FORMATS,
        readings: int | None = 2,
        pages: int = 64 << 20,
        waiting: int = 8,
        naming: Sequence[type[Artifact]] = (),
        pace: Pace | None = None,
        gauge: Gauge | None = None,
    ) -> None:
        if edit_ttl.total_seconds() <= deadline:
            raise ValueError("an edit's lease must outlast the app's deadline, and the commit")
        self._apps: Mapping[type[NativeFile], App] = (
            dict(app) if isinstance(app, Mapping) else {NativeFile: app}
        )
        if not self._apps:
            raise ValueError("native files need an app to read them")
        self._blobs = blobs
        self._checkouts = checkouts
        self._checkout_ttl = checkout_ttl
        self._deadline = deadline
        self._edit_ttl = edit_ttl
        self._keep = keep
        self._clock = clock
        self._integrations = integrations
        self._formats = formats
        self._readings = readings
        self._reading: Counter[str] = Counter()
        self._waiting_most = waiting
        self._waiting: Counter[str] = Counter()
        self._pages_most = pages
        self._pages: OrderedDict[PageKey, bytes] = OrderedDict()
        self._pages_held = 0
        self._naming: tuple[type[Artifact], ...] = (NativeFile, *naming)
        self._pace = pace
        self._gauge = gauge

    def waiting(self, tenant_id: str) -> int:
        """How many of the tenant's pages wait for one of its readings now."""
        return self._waiting[tenant_id]

    @property
    def readings(self) -> int | None:
        """How many files each tenant may have the app read at once, or None for no limit."""
        return self._readings

    @property
    def pace(self) -> Pace | None:
        """How many files each person may start in a minute, if it is paced here."""
        return self._pace

    @property
    def gauge(self) -> Gauge | None:
        """How many files this process makes at once, if it is held to a number here."""
        return self._gauge

    @property
    def limit(self) -> int:
        """The largest file, in bytes, that the blob store keeps."""
        return self._blobs.limit

    def app_of(self, file_type: type[NativeFile]) -> App:
        """The app that reads a native type: its own, or else its nearest base's.

        Raises:
            ValidationFailed: If no app reads it.
        """
        for base in file_type.__mro__:
            if (app := self._apps.get(cast(type[NativeFile], base))) is not None:
                return app
        raise ValidationFailed(f"no app reads a {file_type.kind}", [])

    def extensions(self, file_type: type[NativeFile]) -> list[str]:
        """The extensions of a native type's formats that uploads are told by; none if no app."""
        try:
            self.app_of(file_type)
        except ValidationFailed:
            return []
        formats = self._formats
        return sorted(formats[m].extension for m in file_type.formats if m in formats)

    # ─── the switch ───────────────────────────────────────────────────────────

    async def enabled(self, ws: Workspace, file_type: type[NativeFile] | None = None) -> bool:
        """Whether the app of a native type is on in the workspace; or, without one, any app.

        A type no app reads is off.
        """
        try:
            apps = list(self._apps.values()) if file_type is None else [self.app_of(file_type)]
        except ValidationFailed:
            return False
        if self._integrations is None:
            return True
        for app in apps:
            if await self._integrations.is_enabled(ws.tenant_id, ws.workspace_id, app.integration):
                return True
        return False

    def key_of(self, kind: str, data: Mapping[str, JsonValue]) -> str | None:
        """The integration that governs an artifact: its app's for a native file, else None.

        It is the `key_of` of artifactr's `integration_gate`, so that while a file's app is off,
        an edit of the file is refused on every surface, REST and MCP too, not only here. A
        native type no app reads is governed by none, and no app edits it.
        """
        del data  # a native file's app is its type's
        file_type = artifact_types().get(kind)
        if file_type is None or not issubclass(file_type, NativeFile):
            return None
        try:
            return self.app_of(file_type).integration
        except ValidationFailed:
            return None

    async def _switched_on(self, ws: Workspace, file_type: type[NativeFile]) -> App:
        """The type's app, if it is on in the workspace.

        Raises:
            NotEnabled: If it is off.
        """
        app = self.app_of(file_type)
        if not await self.enabled(ws, file_type):
            raise NotEnabled(app.integration)
        return app

    # ─── uploads ──────────────────────────────────────────────────────────────

    async def upload[F: NativeFile](
        self,
        ws: Workspace,
        file_type: type[F],
        name: str,
        data: AsyncIterable[bytes],
        *,
        media_type: str | None = None,
        artifact_id: ArtifactId | None = None,
        thread_id: ThreadId | None = None,
    ) -> Applied | Proposed | None:
        """Create a native file from uploaded bytes, with a new id unless one is given.

        Without a `media_type`, the format is the one of the type's that the first bytes are,
        never what a client says; either way, the app reads the file before anything is
        committed. The name keeps no path or control character, and takes the format's
        extension. An upload given the id of a native file whose content is these bytes
        commits nothing, so one retried after it succeeded makes nothing twice.

        Returns:
            The new file's outcome, or None if the file with this id is already these bytes.

        Raises:
            NotEnabled: If the app's integration is off in the workspace.
            ValidationFailed: If the type doesn't hold files of `media_type`, no app reads it,
                or its app reads the file as another format.
            InvalidState: If an artifact with this id exists, and isn't these bytes.
            TooLarge: If the file is larger than the blob store's limit.
            OverQuota: If the file would take the workspace or the tenant past a quota.
            AppFailed: `refused` if the first bytes are of none of the type's formats, or the
                app can't read the file.
            Busy: If the tenant has as many files being read as it may.
        """
        app = await self._switched_on(ws, file_type)
        told = media_type is None
        if media_type is None:
            media_type, data = await sniffed(data, self._formats, file_type.formats)
            if media_type is None:
                raise AppFailed("refused", f"the file is not a {file_type.kind}")
        if media_type not in file_type.formats:
            raise ValidationFailed(f"a {file_type.kind} holds {sorted(file_type.formats)}", [])
        content = await spool(data, self._most(media_type))
        if artifact_id is not None and artifact_id in (await ws.hidden()).artifacts:
            # Taken, by a file its uploader can't see: refused as a taken id they can see is,
            # at the same point, before the app reads any of it or anything is stored.
            raise AlreadyExists("artifact", artifact_id)
        if artifact_id is not None and (uploaded := await _existing(ws, artifact_id)):
            if uploaded.data.content.sha256 != hashlib.sha256(content).hexdigest():
                raise AlreadyExists("artifact", artifact_id)
            return None
        inspection = await self._read(ws, app, content)
        if inspection.media_type != media_type and (
            inspection.media_type is not None or (told and not self._formats[media_type].told)
        ):
            # Never the format the app named: it is the worker's text, which a file can shape.
            raise ValidationFailed("the app read the file as another format than its kind's", [])
        known = self._formats.get(media_type)
        name = file_name(name, "" if known is None else known.extension, self._formats)
        artifact_id = artifact_id or new_artifact_id()
        made = Provenance(source="upload")
        manifest = await self._stored(
            ws, artifact_id, file_type, name, (content, media_type), inspection, made
        )
        return await ws.commit(
            create_artifact(manifest, artifact_id=artifact_id, thread_id=thread_id)
        )

    async def create[F: NativeFile](
        self,
        ws: Workspace,
        file_type: type[F],
        name: str,
        *,
        artifact_id: ArtifactId | None = None,
        thread_id: ThreadId | None = None,
    ) -> Applied | Proposed | None:
        """Create a blank native file of a type, as its app makes one, under an id or a new one.

        It is how an agent starts a file to edit (native files ADR-0019). The handle's actor must
        be allowed `artifactr:create_native_file` and `artifactr:create_artifact`, asked before
        anything else. The app makes the file from nothing, `apply` of no commands, in one of
        the tenant's readings, and its format is the one the app names, or the type's only one.
        The name keeps no path or control character, and takes the format's extension. Given
        the id of a file of this type that is there, it makes nothing, before the app is called
        or the pace spent, so a call retried after it succeeded makes one file.

        An agent's run commits it as the person it acts for, so it is applied, not proposed,
        whatever the type's write policy, and is held to their pace and share of places, as
        their uploads are: the provenance, `blank`, records that the app made it, and the agent
        and its run that asked. The agent's edits of it then follow the policy. A run that acts
        for no one commits it as itself, and one for a person's client as the client, each
        under the policy.

        Returns:
            The new file's outcome, or None if a file of this type has this id already.

        Raises:
            Forbidden: If the actor may not create a native file, or an artifact.
            NotEnabled: If the app's integration is off in the workspace.
            AlreadyExists: If an artifact with this id exists, and isn't a file of this type.
            Paced: If the actor is past their pace, or this process holds every place.
            Busy: If the tenant has as many files being read as it may.
            AppFailed: If the app can't make a blank file: `refused` if it makes none.
            ValidationFailed: If the app makes a file of another format than the type's.
            TooLarge: If the file is larger than its format's most.
            OverQuota: If the file would take the workspace or the tenant past a quota.
        """
        await ws.check(Access(action=CREATE_NATIVE_FILE))
        await ws.check(Access(action=CREATE_ARTIFACT))
        app = await self._switched_on(ws, file_type)
        if artifact_id is not None and artifact_id in (await ws.hidden()).artifacts:
            raise AlreadyExists("artifact", artifact_id)
        if artifact_id is not None and (made := await _existing(ws, artifact_id)):
            if not isinstance(made.data, file_type):
                raise AlreadyExists("artifact", artifact_id)
            return None
        committer = _creator(ws)
        with self._admitted(committer):
            async with self._turn(ws.tenant_id):
                blank = await app.apply(None, [], deadline=self._deadline)
            media_type = _blank_format(file_type, blank.inspection)
            if len(blank.content) > (most := self._most(media_type)):
                raise TooLarge(most)
            known = self._formats.get(media_type)
            name = file_name(name, "" if known is None else known.extension, self._formats)
            artifact_id = artifact_id or new_artifact_id()
            asked = ws.actor
            via = asked if committer is not ws and isinstance(asked, AgentActor) else None
            made = Provenance(
                source="blank",
                app=app.name,
                app_version=app.version,
                build=app.build,
                agent=None if via is None else via.participant,
                run_id=None if via is None else via.run_id,
            )
            manifest = await self._stored(
                ws,
                artifact_id,
                file_type,
                name,
                (blank.content, media_type),
                blank.inspection,
                made,
            )
            command = create_artifact(manifest, artifact_id=artifact_id, thread_id=thread_id)
            try:
                return await committer.commit(command)
            except AlreadyExists:
                # The same id, made meanwhile by the same call run twice at once: made once.
                made = await _existing(ws, artifact_id)
                if made is None or not isinstance(made.data, file_type):
                    raise
                return None

    @contextlib.contextmanager
    def _admitted(self, ws: Workspace) -> Generator[None]:
        """Hold a place for the actor's file while it is made, within their pace and share.

        The actor is the one it is committed as, so an agent's run spends its person's pace and
        share, as their uploads do. The place first, as the router takes it: a refusal for want
        of one counts against no one's pace.

        Raises:
            Paced: If no place is free, or the actor is past their pace.
        """
        who = (ws.tenant_id, ws.actor.participant)
        places = contextlib.nullcontext(True) if self._gauge is None else self._gauge.held(who)
        with places as held:
            if not held:
                raise Paced(None)
            if self._pace is not None and (wait := self._pace.admit(who)) is not None:
                raise Paced(wait)
            yield

    # ─── check-out and check-in ───────────────────────────────────────────────

    async def check_out(self, ws: Workspace, artifact_id: ArtifactId) -> Checkout:
        """Check a native file out to the workspace's actor, holding its lease.

        The lease is taken before the head is read, so the version checked out is the one the
        lease holds the file at.

        Raises:
            NotEnabled: If the app's integration is off in the workspace.
            ArtifactBusy: If someone else has the file: a check-out, or an agent's edit.
            NotFound: If there is no such native file, or it is hidden from the actor.
        """
        await self._switched_on(ws, type((await ws.get(NativeFile, artifact_id)).data))
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
            NotEnabled: If the app's integration is off in the workspace.
            NotFound: If there is no such check-out.
            Forbidden: If it is someone else's.
            ArtifactBusy: If its lease ended and someone else has the file now.
            InvalidState: If it was checked in.
        """
        checkout = await self._own(ws, checkout_id)
        await self._switched_on(ws, type((await ws.get(NativeFile, checkout.artifact_id)).data))
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
        media_type: str | None = None,
    ) -> Applied | Proposed | None:
        """Check a file in: a revision from the version checked out, and the lease released.

        The base is the check-out's, never the upload's. The lease is taken again first, which
        renews one that lapsed if no one else took it. A file whose fingerprint is the head's
        commits nothing, so a check-in retried after it succeeded does nothing. A check-in that
        is stale, because its lease lapsed and someone else took the file or committed
        meanwhile, is kept as a proposal against the head, which tests the head's digest and
        records the check-out's base as its provenance. Either way the check-out ends: its
        record is closed and its lease released.

        The file must be in the format checked out: one that says it is another, by
        `media_type`, or that the app reads as another, is refused, and never converted.

        Returns:
            The revision's outcome, a proposal's if it was stale, or None if nothing changed.

        Raises:
            NotEnabled: If the app's integration is off in the workspace.
            NotFound: If there is no such check-out, or its file is hidden from the actor.
            Forbidden: If it is someone else's.
            FormatChanged: If the file is in another format than the one checked out.
            InvalidState: If it was checked in already, and this file is another.
            TooLarge: If the file is larger than the blob store's limit.
            AppFailed: If the app can't read it.
        """
        checkout = await self._own(ws, checkout_id)
        artifact_id = checkout.artifact_id
        head = await ws.get(NativeFile, artifact_id)
        app = await self._switched_on(ws, type(head.data))
        checked_out = head.data.content.media_type
        if media_type not in (None, checked_out):
            raise FormatChanged(artifact_id, checked_out=checked_out, checked_in=media_type)
        content = await spool(data, self._most(checked_out))
        inspection = await self._read(ws, app, content)
        if inspection.media_type not in (None, checked_out):
            # The app's name for a format is the worker's text: only one known is told.
            read = inspection.media_type
            told = read if read in self._formats else "another format"
            raise FormatChanged(artifact_id, checked_out=checked_out, checked_in=told)
        if inspection.fingerprint == head.data.fingerprint:
            await self._close(ws, checkout)
            return None
        if checkout.checked_in:
            raise InvalidState(f"checkout {checkout_id} was checked in: check the file out again")
        made = Provenance(source="check_in", base=checkout.base_sha256)
        after = await self._stored(
            ws,
            artifact_id,
            type(head.data),
            head.data.name,
            (content, checked_out),
            inspection,
            made,
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
            NotEnabled: If the app's integration is off in the workspace.
            NotFound: If there is no such native file, or it is hidden from the actor.
            VersionConflict: If `base_version` isn't the head's: the agent plans again.
            ArtifactBusy: If someone else has the file, such as a person's check-out. The agent
                plans again after the check-in, or at once if the busy lease is None.
            ContentUnavailable: If the head's bytes aren't in the blob store.
            AppFailed: If the app can't run the batch.
        """
        app = await self._switched_on(ws, type((await ws.get(NativeFile, artifact_id)).data))
        holder = f"edit:{uuid.uuid4()}"
        try:
            await ws.lease_artifact(artifact_id, holder=holder, ttl=self._edit_ttl)
            head = await ws.get(NativeFile, artifact_id)
            if head.version != base_version:
                raise VersionConflict(artifact_id, base=base_version, head=head.version)
            scope = _scope(ws)
            source = await self._bytes(scope, artifact_id, head.data.content, "content")
            applied = await app.apply(source, commands, deadline=self._deadline)
            if applied.inspection.fingerprint == head.data.fingerprint:
                return None
            batch: list[JsonValue] = [command.model_dump(mode="json") for command in commands]
            made = Provenance(
                source="commands",
                app=app.name,
                app_version=app.version,
                build=app.build,
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
        manifest = await _manifest_at(ws, artifact_id, version)
        parts = {"content": manifest.content, "text": manifest.text, "review": manifest.review}
        return await self._bytes(_scope(ws), artifact_id, parts[part], part)

    async def render(
        self,
        ws: Workspace,
        artifact_id: ArtifactId,
        page: int,
        *,
        version: int | None = None,
        admit: Callable[[], None] | None = None,
    ) -> bytes:
        """Render one page of a native file, from 1, at its head or a version, as a PNG.

        A page rendered before, of the same bytes, is given again without the app. Otherwise
        `admit` is called, which may refuse by raising, and the app renders it in one of the
        tenant's readings.

        Raises:
            NotFound: If there is no such native file, or it is hidden.
            ContentUnavailable: If the blob store doesn't have its bytes.
            AppFailed: If the app can't render it, or there is no such page.
            Busy: If the tenant has as many files being read or rendered as it may.
        """
        manifest = await _manifest_at(ws, artifact_id, version)
        app = self.app_of(type(manifest))
        key = _page_key(ws, artifact_id, app, manifest.content.sha256, page)
        if (png := self._page(key)) is not None:
            return png

        async def source() -> bytes:
            return await self._bytes(_scope(ws), artifact_id, manifest.content, "content")

        return await self._rendered(ws, app, key, source, admit)

    async def proposed(
        self, ws: Workspace, proposal_id: ProposalId, *, part: Part = "content"
    ) -> bytes:
        """Return what a proposal would make of a native file: its bytes, its text or its review.

        A stale check-in is kept as a proposal, and its reviewer reads it beside the head. The
        proposal is read through the workspace, and then its file, as a read of either is, so a
        hidden one is answered as a missing one.

        Raises:
            NotFound: If there is no such proposal, it is to no native file, or either is hidden.
            ContentUnavailable: If the proposal names nothing for `part`, as one that doesn't
                edit the file's content, or bytes the blob store doesn't have.
        """
        return (await self._proposed(ws, proposal_id, part))[0]

    async def render_proposed(
        self,
        ws: Workspace,
        proposal_id: ProposalId,
        page: int,
        *,
        admit: Callable[[], None] | None = None,
    ) -> bytes:
        """Render one page of what a proposal would make of a native file, from 1, as a PNG.

        As `render` does: a page rendered before is given again, and `admit` is called before
        one reaches the app.

        Raises:
            NotFound: If there is no such proposal, it is to no native file, or either is hidden.
            ContentUnavailable: If the proposal names no content, or the blob store hasn't it.
            AppFailed: If the app can't render it, or there is no such page.
            Busy: If the tenant has as many files being read or rendered as it may.
        """
        artifact_id, named, file_type = await self._proposed_blob(ws, proposal_id, "content")
        if named is None:  # a proposal that doesn't change the file's content has no page of it
            raise ContentUnavailable(artifact_id, "content")
        app = self.app_of(file_type)
        key = _page_key(ws, artifact_id, app, named.sha256, page)
        if (png := self._page(key)) is not None:
            return png

        async def proposed() -> bytes:
            return await self._bytes(_scope(ws), artifact_id, named, "content")

        return await self._rendered(ws, app, key, proposed, admit)

    async def proposed_commands(
        self, ws: Workspace, proposal_id: ProposalId
    ) -> ProposalDescription:
        """Say what an agent's proposal on a native file does: a line, and each of its commands.

        The batch is read from the blob its provenance names, as it was applied, and said in its
        app's words (native files ADR-0020). It is read as `proposed` reads, so a hidden
        proposal, or one to a hidden file, is answered as a missing one.

        Raises:
            NotFound: If there is no such proposal, it is to no native file, or either is hidden.
            ContentUnavailable: If the proposal was made by no commands, as a person's check-in,
                or names a batch the blob store doesn't have, larger than `BATCH_MOST`, or that
                holds no commands; or its provenance isn't one.
        """
        proposal = await ws.proposal(proposal_id)
        await ws.get(NativeFile, proposal.artifact_id)
        change = proposal.change
        made = _provenance(change.patch) if isinstance(change, EditArtifact) else None
        if made is None or made.commands is None or made.commands.size > BATCH_MOST:
            raise ContentUnavailable(proposal.artifact_id, "commands")
        batch = await self._bytes(_scope(ws), proposal.artifact_id, made.commands, "commands")
        try:
            commands = _COMMANDS.validate_json(batch)
        except ValidationError:
            raise ContentUnavailable(proposal.artifact_id, "commands") from None
        return describe(made.app, commands)

    def _page(self, key: PageKey) -> bytes | None:
        """A page rendered before, if this process still keeps it."""
        png = self._pages.get(key)
        if png is not None:
            self._pages.move_to_end(key)
        return png

    async def _rendered(
        self,
        ws: Workspace,
        app: App,
        key: PageKey,
        source: Callable[[], Awaitable[bytes]],
        admit: Callable[[], None] | None,
    ) -> bytes:
        """Render a page in one of the tenant's readings, and keep it, the oldest let go first.

        A page waits a while for a reading, as a viewer's pages are asked for a few at once,
        and is counted against its reader's pace only once it has one.
        """
        *_, page, scale = key
        async with self._turn(ws.tenant_id, wait=self._deadline):
            # Rendered by another while this one waited for its reading: given that one.
            if (kept := self._page(key)) is not None:
                return kept
            if admit is not None:
                admit()
            png = await app.render(await source(), page, scale=scale, deadline=self._deadline)
        if len(png) <= self._pages_most and key not in self._pages:
            self._pages[key] = png
            self._pages_held += len(png)
            while self._pages_held > self._pages_most:
                self._pages_held -= len(self._pages.popitem(last=False)[1])
        return png

    async def _proposed(
        self, ws: Workspace, proposal_id: ProposalId, part: Part
    ) -> tuple[bytes, type[NativeFile]]:
        """What a proposal would make of a part of a native file, and the file's type."""
        artifact_id, named, file_type = await self._proposed_blob(ws, proposal_id, part)
        return await self._bytes(_scope(ws), artifact_id, named, part), file_type

    async def _proposed_blob(
        self, ws: Workspace, proposal_id: ProposalId, part: Part
    ) -> tuple[ArtifactId, Blob | None, type[NativeFile]]:
        """The file a proposal is to, the blob it names for a part, if any, and the file's type."""
        proposal = await ws.proposal(proposal_id)
        head = await ws.get(NativeFile, proposal.artifact_id)
        change = proposal.change
        named = _replaced(change.patch, part) if isinstance(change, EditArtifact) else None
        return proposal.artifact_id, named, type(head.data)

    # ─── collection ───────────────────────────────────────────────────────────

    async def collect(self, ws: Workspace) -> int:
        """Delete the workspace's blobs that nothing names, unless they were put lately.

        Named means by a pending proposal, or by any revision of a native file, or of a type
        `naming` adds, archived ones too; the proposals are read first, so that one accepted
        meanwhile is read as a revision. Bytes put within `keep` are kept whatever names them, for
        the commit that follows a put. The handle must see every thread and artifact, as an
        application's own actor does: a blob that only a hidden revision names would otherwise be
        lost.

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
        for kind in self._naming:
            for artifact in await ws.artifacts(kind, include_archived=True):
                for revision in await ws.revisions(artifact.id):
                    referenced |= {(artifact.id, sha256) for sha256 in digests(revision.data)}
        deleted = await self._blobs.collect(_scope(ws), referenced, before=before)
        # The pages kept of bytes nothing names go too, so a page is never given for a digest
        # whose bytes the store no longer has.
        for key in [
            key
            for key in self._pages
            if key[:2] == (ws.tenant_id, ws.workspace_id) and (key[2], key[4]) not in referenced
        ]:
            self._pages_held -= len(self._pages.pop(key))
        return deleted

    # ─── what every write shares ──────────────────────────────────────────────

    def most(self, file_type: type[NativeFile]) -> int:
        """The most bytes a file of a native type holds, of any of its formats."""
        return max(self._most(media_type) for media_type in file_type.formats)

    def _most(self, media_type: str) -> int:
        """The most bytes a file of a format holds: its own most, if fewer than the store's."""
        known = self._formats.get(media_type)
        most = None if known is None else known.most
        return self._blobs.limit if most is None else min(most, self._blobs.limit)

    async def _read(self, ws: Workspace, app: App, content: bytes) -> Inspection:
        """What the app reads of a file not yet stored, in one of the tenant's readings."""
        async with self._turn(ws.tenant_id):
            return await app.inspect(content, deadline=self._deadline)

    async def _stored[F: NativeFile](
        self,
        ws: Workspace,
        artifact_id: ArtifactId,
        file_type: type[F],
        name: str,
        content: tuple[bytes, str],
        inspection: Inspection,
        provenance: Provenance,
    ) -> F:
        """Store a file the app has read, with its words and review, whole or not at all.

        Only a file the app read is stored, so one refused before holds nothing against a quota.
        """
        stored, text, review = await self._blobs.put_all(
            _scope(ws),
            artifact_id,
            [content, (inspection.text.encode(), TEXT), (_canonical(inspection.review), JSON)],
        )
        return file_type(
            name=name,
            content=stored,
            fingerprint=inspection.fingerprint,
            text=text,
            review=review,
            outline=inspection.outline,
            pages=inspection.pages,
            provenance=provenance,
        )

    @contextlib.asynccontextmanager
    async def _turn(self, tenant_id: str, *, wait: float = 0.0) -> AsyncGenerator[None]:
        """Hold one of the tenant's readings while the app reads a file.

        Without one free, it waits up to `wait` seconds for one, then refuses; so does one past
        the tenant's waiting, at once. The waiters look again every `LOOK_AGAIN` seconds, not
        in turn: whichever looks first after a reading is freed takes it (files ADR-0018).

        Raises:
            Busy: If the tenant has all of its readings, for all of the wait, or as many pages
                waiting as it may.
        """
        readings = self._readings
        if readings is not None and self._reading[tenant_id] >= readings:
            if wait <= 0 or self._waiting[tenant_id] >= self._waiting_most:
                raise Busy(readings)
            # Looked at again every so often, not woken: an application may serve requests on
            # several event loops, and a waiter tied to one can't be woken from another.
            self._waiting[tenant_id] += 1
            try:
                until = time.monotonic() + wait
                while self._reading[tenant_id] >= readings:
                    left = until - time.monotonic()
                    if left <= 0:
                        raise Busy(readings)
                    await asyncio.sleep(min(LOOK_AGAIN, left))
            finally:
                self._waiting[tenant_id] -= 1
        self._reading[tenant_id] += 1
        try:
            yield
        finally:
            self._reading[tenant_id] -= 1

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
        return await self._blobs.put(scope, artifact_id, once(_canonical(value)), JSON)

    async def _bytes(
        self,
        scope: Scope,
        artifact_id: ArtifactId,
        blob: Blob | None,
        part: Part | Literal["commands"],
    ) -> bytes:
        found = None if blob is None else await self._blobs.get(scope, artifact_id, blob.sha256)
        if found is None:
            raise ContentUnavailable(artifact_id, part)
        return found


def _page_key(ws: Workspace, artifact_id: ArtifactId, app: App, sha256: str, page: int) -> PageKey:
    """Where a page of a file's bytes is kept: by the blob, as the blob store keeps it.

    The blob store keeps bytes by tenant, workspace, file and digest, so a page is kept and found
    by all four too. A digest a proposal names is the proposer's to write, so a page kept for one
    file's bytes is never given for another's that names the same digest. A page kept for a file
    is a render of bytes that file holds: collection drops the pages of the bytes it may delete,
    those nothing names, so a digest whose bytes are gone finds no page and is refused.
    """
    return (ws.tenant_id, ws.workspace_id, artifact_id, app.name, sha256, page, 1.0)


def _canonical(value: JsonValue) -> bytes:
    """A value as canonical JSON: keys sorted, no spaces."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


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


def _replaced(patch: Patch, part: Part) -> Blob | None:
    """The blob a native file's revision gives one of its parts, as `revise` builds it, if any.

    JSON Patch applies its operations in order, so the last that replaces the part is what the
    revision would make. The proposed manifest was validated as the proposal was made, so what it
    names is a blob, or None for a part it clears.
    """
    if not isinstance(patch, JsonPatch):
        return None
    for op in reversed(patch.ops):
        if op.get("op") == "replace" and op.get("path") == f"/{part}":
            value = op.get("value")
            return None if value is None else Blob.model_validate(value)
    return None


def _provenance(patch: Patch) -> Provenance | None:
    """The provenance a native file's revision gives it, as `revise` builds it, if it reads as one.

    As `_replaced` reads a part, the last operation that replaces it is what the revision makes.
    The proposed manifest was validated as the proposal was made, but a proposal is a claim any
    surface writes, so one that isn't a provenance is read as none.
    """
    if not isinstance(patch, JsonPatch):
        return None
    for op in reversed(patch.ops):
        if op.get("op") == "replace" and op.get("path") == "/provenance":
            try:
                return Provenance.model_validate(op.get("value"))
            except ValidationError:
                return None
    return None


def _blank_format(file_type: type[NativeFile], inspection: Inspection) -> str:
    """The format of a blank file its app made: the one it names, or else the type's only one.

    Raises:
        ValidationFailed: If the app names a format the type doesn't hold, or names none of a
            type of several.
    """
    named = inspection.media_type
    if named is None and len(file_type.formats) == 1:
        (named,) = file_type.formats
    if named is None or named not in file_type.formats:
        # Never the format the app named: it is the worker's text.
        raise ValidationFailed(f"the app made a file of another format than a {file_type.kind}", [])
    return named


def _creator(ws: Workspace) -> Workspace:
    """The handle a created file is committed through: an agent's run's person's, or its own.

    The run's actor was checked first, so the file is made only if the agent may make it, and
    the commit asks as the person too.
    """
    actor = ws.actor
    if isinstance(actor, AgentActor) and actor.on_behalf_of is not None:
        return ws.as_actor(actor.on_behalf_of)
    return ws


async def _existing(ws: Workspace, artifact_id: ArtifactId) -> Versioned[NativeFile] | None:
    """The native file with this id, if there is one the actor sees."""
    try:
        return await ws.get(NativeFile, artifact_id)
    except NotFound:
        return None


def _scope(ws: Workspace) -> Scope:
    return Scope(ws.tenant_id, ws.workspace_id)


async def _manifest_at(ws: Workspace, artifact_id: ArtifactId, version: int | None) -> NativeFile:
    """A native file's manifest at its head, or at one of its versions."""
    head = await ws.get(NativeFile, artifact_id)
    return head.data if version in (None, head.version) else await _at(ws, head, version)


async def _at(ws: Workspace, head: Versioned[NativeFile], version: int) -> NativeFile:
    """A native file's manifest at one of its versions."""
    for revision in await ws.revisions(head.id):
        if revision.version == version:
            return type(head.data).model_validate(revision.data)
    raise NotFound("revision", f"{head.id}@{version}")
