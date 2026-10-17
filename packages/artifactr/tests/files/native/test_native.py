"""Native files in a workspace, with the fake app, over every store.

Uploads; a person's check-out and check-in, fresh, stale, unchanged and retried; an agent's
edit, refused as busy while the file is checked out; reads; and the collection of what nothing
names.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import override

import pytest

from artifactr.core import (
    Actor,
    AgentActor,
    Applied,
    ArtifactChanged,
    Forbidden,
    InvalidState,
    NotFound,
    PatchFailed,
    Proposed,
    RespondToProposal,
    TenantId,
    UserActor,
    ValidationFailed,
    VersionConflict,
    Visibility,
    WorkspaceId,
    acting_for,
)
from artifactr.files.app import AppCommand, AppFailed, FakeApp
from artifactr.files.blobs import once
from artifactr.files.checkouts import Checkout, InMemoryCheckouts
from artifactr.files.manifest import DOCX, Blob, WordDocument
from artifactr.files.native import ContentUnavailable, NativeFiles
from artifactr.files.native.files import digests
from artifactr.workspace import (
    Access,
    ArtifactBusy,
    InMemoryStorage,
    Scope,
    Workspace,
    Workspaces,
)
from tests.files.clock import FakeClock
from tests.files.conftest import Stores

ALICE = UserActor(id="alice", name="Alice")
BOB = UserActor(id="bob", name="Bob")
AGENT = AgentActor(thread_id="t1", run_id="r1", on_behalf_of=ALICE)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def add(text: str) -> AppCommand:
    return AppCommand(name="add_paragraph", args={"text": text})


@dataclass
class World:
    """Alice's handle on a workspace with a Word document, `a1`, uploaded at version 1."""

    ws: Workspace
    files: NativeFiles
    stores: Stores
    clock: FakeClock

    @property
    def agent(self) -> Workspace:
        return self.ws.as_actor(AGENT)

    @property
    def scope(self) -> Scope:
        return Scope(self.ws.tenant_id, self.ws.workspace_id)

    async def head(self) -> WordDocument:
        return (await self.ws.get(WordDocument, "a1")).data

    async def summary(self) -> str:
        """The change note of the file's last change."""
        [*_, changed] = [
            e.event for e in await self.ws.read() if e.event.type == "artifact_changed"
        ]
        assert isinstance(changed, ArtifactChanged)
        return changed.summary

    async def accept(self, outcome: Applied | Proposed | None, *, by: Actor = BOB) -> None:
        """Accept a proposal, as someone other than its author: Bob, unless told."""
        assert isinstance(outcome, Proposed)
        accepted = RespondToProposal(proposal_id=outcome.proposal_id, decision="accept")
        await self.ws.as_actor(by).commit(accepted)


async def _world(stores: Stores, clock: FakeClock, workspaces: Workspaces) -> World:
    files = NativeFiles(stores.blobs, stores.checkouts, FakeApp(), clock=clock)
    ws = await workspaces.open("acme", "w1", actor=ALICE)
    uploaded = await files.upload(
        ws,
        WordDocument,
        "contract.docx",
        once(FakeApp.file("Terms")),
        media_type=DOCX,
        artifact_id="a1",
    )
    assert isinstance(uploaded, Applied)
    return World(ws, files, stores, clock)


@pytest.fixture
async def world(stores: Stores, clock: FakeClock) -> World:
    return await _world(stores, clock, Workspaces(InMemoryStorage(clock=clock)))


# ─── uploads ─────────────────────────────────────────────────────────────────


async def test_an_upload_is_a_manifest_over_its_bytes(world: World) -> None:
    head = await world.head()
    assert head.name == "contract.docx"
    assert head.content.media_type == DOCX
    assert head.provenance.source == "upload"
    assert (head.outline, head.pages) == ("Terms", 1)
    assert await world.files.read(world.ws, "a1") == FakeApp.file("Terms")
    assert await world.files.read(world.ws, "a1", part="text") == b"Terms"
    assert await world.files.read(world.ws, "a1", part="review") == b'{"comments":[]}'
    [revision] = await world.ws.revisions("a1")
    assert b"paragraphs" not in revision.model_dump_json().encode(), "no bytes in the log"


async def test_an_agents_upload_is_a_proposal(world: World) -> None:
    proposed = await world.files.upload(
        world.agent, WordDocument, "draft.docx", once(FakeApp.file("Draft")), media_type=DOCX
    )
    assert isinstance(proposed, Proposed)


async def test_an_upload_is_of_the_types_format(world: World) -> None:
    with pytest.raises(ValidationFailed, match="word_document"):
        await world.files.upload(
            world.ws, WordDocument, "notes.txt", once(b"notes"), media_type="text/plain"
        )


# ─── check-out and check-in ──────────────────────────────────────────────────


async def test_a_check_out_holds_the_file_for_eight_hours(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    head = await world.head()
    assert (checkout.base_version, checkout.base_sha256) == (1, head.content.sha256)
    assert checkout.actor == ALICE
    assert checkout.expires_at == world.clock.now + 8 * HOUR
    lease = await world.ws.artifact_lease("a1")
    assert lease is not None
    assert (lease.holder, lease.expires_at) == (checkout.holder, checkout.expires_at)
    assert lease.holder == f"checkout:{checkout.id}:user:alice"
    assert await world.stores.checkouts.get(world.scope, checkout.id) == checkout


async def test_two_check_outs_are_two_holders(world: World) -> None:
    await world.files.check_out(world.ws, "a1")
    with pytest.raises(ArtifactBusy):  # in another tab
        await world.files.check_out(world.ws, "a1")


async def test_a_check_in_commits_from_the_version_checked_out(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    file = FakeApp.file("Terms", "Fees")
    assert isinstance(await world.files.check_in(world.ws, checkout.id, once(file)), Applied)
    head = await world.head()
    assert head.provenance.source == "check_in"
    assert head.provenance.base == checkout.base_sha256
    assert head.outline == "Terms\nFees"
    [*_, revision] = await world.ws.revisions("a1")
    assert revision.actor == ALICE
    assert await world.summary() == "Checked in contract.docx"
    assert await world.ws.artifact_lease("a1") is None, "the lease is released"


async def test_a_check_in_names_its_change(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    await world.files.check_in(
        world.ws, checkout.id, once(FakeApp.file("Fees")), summary="Fees added"
    )
    assert await world.summary() == "Fees added"


async def test_a_save_that_changes_nothing_makes_no_revision(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    resaved = (await FakeApp().apply(FakeApp.file("Terms"), [], deadline=1)).content
    assert resaved != FakeApp.file("Terms"), "the bytes differ: the save stamped them"
    assert await world.files.check_in(world.ws, checkout.id, once(resaved)) is None
    assert len(await world.ws.revisions("a1")) == 1
    assert await world.ws.artifact_lease("a1") is None


async def test_a_retried_check_in_does_nothing_again(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    file = FakeApp.file("Terms", "Fees")
    assert isinstance(await world.files.check_in(world.ws, checkout.id, once(file)), Applied)
    assert await world.files.check_in(world.ws, checkout.id, once(file)) is None
    assert len(await world.ws.revisions("a1")) == 2


async def test_a_check_out_ends_when_it_is_checked_in(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    await world.files.check_in(world.ws, checkout.id, once(FakeApp.file("Terms", "Fees")))
    closed = await world.stores.checkouts.get(world.scope, checkout.id)
    assert closed is not None
    assert closed.checked_in
    with pytest.raises(InvalidState, match="check the file out again"):
        await world.files.extend(world.ws, checkout.id)
    with pytest.raises(InvalidState, match="check the file out again"):
        await world.files.check_in(world.ws, checkout.id, once(FakeApp.file("Another")))
    assert await world.ws.artifact_lease("a1") is None


async def test_a_check_in_after_another_took_the_file_is_a_proposal(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    world.clock.advance(9 * HOUR)
    bobs = await world.files.check_out(world.ws.as_actor(BOB), "a1")  # nothing committed yet
    stale = await world.files.check_in(world.ws, checkout.id, once(FakeApp.file("Terms", "Fees")))
    assert isinstance(stale, Proposed)
    assert len(await world.ws.revisions("a1")) == 1, "Bob's check-out isn't overwritten"
    lease = await world.ws.artifact_lease("a1")
    assert lease is not None
    assert lease.holder == bobs.holder


async def test_a_lapsed_check_out_no_one_took_is_checked_in(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    world.clock.advance(9 * HOUR)
    file = FakeApp.file("Terms", "Fees")
    assert isinstance(await world.files.check_in(world.ws, checkout.id, once(file)), Applied)


async def test_a_stale_check_in_is_a_proposal_against_the_head(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    world.clock.advance(9 * HOUR)  # the check-out's lease lapses, and an agent edits
    await world.accept(
        await world.files.edit(world.agent, "a1", base_version=1, commands=[add("x")], summary="x")
    )
    head = await world.ws.get(WordDocument, "a1")
    file = FakeApp.file("Terms", "Fees")
    stale = await world.files.check_in(world.ws, checkout.id, once(file))
    assert isinstance(stale, Proposed)
    proposal = await world.ws.proposal(stale.proposal_id)
    assert proposal.proposed_by == ALICE, "the one proposal from a person"
    assert proposal.rationale is not None
    assert "version 1" in proposal.rationale
    change = proposal.change.model_dump(mode="json")
    assert change["base_version"] == head.version
    ops = change["patch"]["ops"]
    assert ops[0]["value"] == head.data.content.sha256, "it tests the head's digest"
    provenance = next(op["value"] for op in ops if op["path"] == "/provenance")
    assert provenance["base"] == checkout.base_sha256, "made from the check-out's"
    await world.accept(stale)
    assert (await world.head()).outline == "Terms\nFees"


async def test_a_stale_check_in_the_head_already_has_does_nothing(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    world.clock.advance(9 * HOUR)
    await world.accept(
        await world.files.edit(
            world.agent, "a1", base_version=1, commands=[add("Fees")], summary="Fees"
        )
    )
    file = FakeApp.file("Terms", "Fees")
    assert await world.files.check_in(world.ws, checkout.id, once(file)) is None


async def test_a_stale_check_in_the_head_reached_meanwhile_does_nothing(
    stores: Stores, clock: FakeClock
) -> None:
    file = FakeApp.file("Terms", "Fees")
    armed = True

    async def meanwhile(
        tenant: TenantId, workspace: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        """As Alice's check-in commits, Bob edits the file to what she checks in."""
        nonlocal armed
        if armed and actor == ALICE and access.action == "artifactr:edit_artifact":
            armed = False
            bob = world.ws.as_actor(BOB)
            await world.files.edit(bob, "a1", base_version=1, commands=[add("Fees")], summary="x")
        return True

    workspaces = Workspaces(InMemoryStorage(clock=clock), authorize=meanwhile)
    world = await _world(stores, clock, workspaces)
    armed = False
    checkout = await world.files.check_out(world.ws, "a1")
    clock.advance(9 * HOUR)
    armed = True
    assert await world.files.check_in(world.ws, checkout.id, once(file)) is None
    assert not armed
    assert len(await world.ws.revisions("a1")) == 2, "Bob's edit alone"
    assert await world.ws.proposals(status="pending") == []


async def test_a_check_out_is_extended_by_its_holder(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    world.clock.advance(7 * HOUR)
    extended = await world.files.extend(world.ws, checkout.id)
    assert extended.expires_at == world.clock.now + 8 * HOUR
    assert await world.stores.checkouts.get(world.scope, checkout.id) == extended
    lease = await world.ws.artifact_lease("a1")
    assert lease is not None
    assert lease.expires_at == extended.expires_at


async def test_a_lapsed_check_out_taken_by_another_is_not_extended(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    world.clock.advance(9 * HOUR)
    await world.files.check_out(world.ws.as_actor(BOB), "a1")
    with pytest.raises(ArtifactBusy):
        await world.files.extend(world.ws, checkout.id)


async def test_a_check_out_is_its_holders(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    bob = world.ws.as_actor(BOB)
    with pytest.raises(Forbidden):
        await world.files.extend(bob, checkout.id)
    with pytest.raises(Forbidden):
        await world.files.check_in(bob, checkout.id, once(FakeApp.file("Bob's")))
    with pytest.raises(NotFound):
        await world.files.check_in(world.ws, "co_none", once(FakeApp.file("x")))


class Failing(InMemoryCheckouts):
    """Check-outs that can't be kept."""

    @override
    async def save(self, scope: Scope, checkout: Checkout) -> None:
        raise ConnectionError("the database is out of reach")


async def test_a_check_out_that_fails_releases_its_lease(world: World) -> None:
    files = NativeFiles(world.stores.blobs, Failing(), FakeApp())
    with pytest.raises(ConnectionError):
        await files.check_out(world.ws, "a1")
    assert await world.ws.artifact_lease("a1") is None


# ─── agents' edits ───────────────────────────────────────────────────────────


async def test_an_agents_edit_is_a_proposal_by_the_apps_commands(world: World) -> None:
    proposed = await world.files.edit(
        world.agent, "a1", base_version=1, commands=[add("Fees")], summary="Added the fees"
    )
    assert await world.ws.artifact_lease("a1") is None, "the edit's lease is released"
    await world.accept(proposed)
    head = await world.head()
    assert head.outline == "Terms\nFees"
    made = head.provenance
    assert (made.source, made.app, made.app_version) == ("commands", "fake", "1.0")
    assert made.build is None
    assert made.commands is not None
    batch = await world.stores.blobs.get(world.scope, "a1", made.commands.sha256)
    assert batch == b'[{"args":{"text":"Fees"},"name":"add_paragraph"}]'
    assert await world.summary() == "Added the fees"


async def test_a_persons_edit_by_commands_is_applied(world: World) -> None:
    applied = await world.files.edit(
        world.ws, "a1", base_version=1, commands=[add("Fees")], summary="Fees"
    )
    assert isinstance(applied, Applied)


async def test_an_agent_is_refused_as_busy_while_the_file_is_checked_out(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    with pytest.raises(ArtifactBusy) as busy:
        await world.files.edit(world.agent, "a1", base_version=1, commands=[add("x")], summary="x")
    assert busy.value.lease is not None
    assert busy.value.lease.holder == checkout.holder, "it says who has the file"
    assert await world.ws.artifact_lease("a1") == busy.value.lease, "the check-out's is kept"
    await world.files.check_in(world.ws, checkout.id, once(FakeApp.file("Terms", "Fees")))
    with pytest.raises(VersionConflict):  # the agent plans again, against the new head
        await world.files.edit(world.agent, "a1", base_version=1, commands=[add("x")], summary="x")
    again = await world.files.edit(
        world.agent, "a1", base_version=2, commands=[add("x")], summary="x"
    )
    assert isinstance(again, Proposed)


async def test_a_batch_that_changes_nothing_makes_no_revision(world: World) -> None:
    assert await world.files.edit(world.ws, "a1", base_version=1, commands=[], summary="x") is None
    assert len(await world.ws.revisions("a1")) == 1


async def test_an_app_that_fails_releases_the_lease(world: World) -> None:
    files = NativeFiles(world.stores.blobs, world.stores.checkouts, FakeApp(fails="timeout"))
    with pytest.raises(AppFailed, match="timeout"):
        await files.edit(world.agent, "a1", base_version=1, commands=[add("x")], summary="x")
    assert await world.ws.artifact_lease("a1") is None


async def test_accepting_a_stale_edit_fails_and_one_made_at_the_head_applies(
    world: World,
) -> None:
    first = await world.files.edit(
        world.agent, "a1", base_version=1, commands=[add("Fees")], summary="Fees"
    )
    stale = await world.files.edit(
        world.agent, "a1", base_version=1, commands=[add("Dates")], summary="Dates"
    )
    await world.accept(first)
    with pytest.raises(PatchFailed):
        await world.accept(stale)
    rebuilt = await world.files.edit(
        world.agent, "a1", base_version=2, commands=[add("Dates")], summary="Dates"
    )
    await world.accept(rebuilt)
    assert (await world.head()).outline == "Terms\nFees\nDates"


# ─── missing content, and reads ──────────────────────────────────────────────


async def _hand_written(world: World, content: Blob | None, field: str = "content") -> None:
    """A manifest committed by hand, as `edit_artifact` over REST could, naming any bytes."""
    head = await world.ws.get(WordDocument, "a1")
    await world.ws.commit(head.edit(lambda data: setattr(data, field, content)))


async def test_content_the_store_doesnt_have_is_unavailable(world: World) -> None:
    head = await world.head()
    await _hand_written(world, head.content.model_copy(update={"sha256": "0" * 64}))
    with pytest.raises(ContentUnavailable) as unavailable:
        await world.files.read(world.ws, "a1")
    assert (unavailable.value.artifact_id, unavailable.value.part) == ("a1", "content")
    with pytest.raises(ContentUnavailable):
        await world.files.edit(world.agent, "a1", base_version=2, commands=[add("x")], summary="x")
    assert await world.ws.artifact_lease("a1") is None


async def test_a_revision_without_text_has_none_to_read(world: World) -> None:
    await _hand_written(world, None, "text")
    with pytest.raises(ContentUnavailable, match="text"):
        await world.files.read(world.ws, "a1", part="text")


async def test_any_version_is_read_through_its_revision(world: World) -> None:
    edited = await world.files.edit(
        world.ws, "a1", base_version=1, commands=[add("Fees")], summary="x"
    )
    assert isinstance(edited, Applied)
    assert await world.files.read(world.ws, "a1", version=1) == FakeApp.file("Terms")
    assert await world.files.read(world.ws, "a1", version=2, part="text") == b"Terms\n\nFees"
    with pytest.raises(NotFound, match="a1@3"):
        await world.files.read(world.ws, "a1", version=3)


async def test_a_hidden_file_answers_as_a_missing_one(stores: Stores, clock: FakeClock) -> None:
    async def hidden(tenant: TenantId, workspace: WorkspaceId, actor: Actor) -> Visibility:
        return Visibility(artifacts=frozenset({"a1"} if acting_for(actor) == BOB else ()))

    workspaces = Workspaces(InMemoryStorage(clock=clock), hidden=hidden)
    world = await _world(stores, clock, workspaces)
    bob = world.ws.as_actor(BOB)
    with pytest.raises(NotFound):
        await world.files.read(bob, "a1")
    with pytest.raises(NotFound):
        await world.files.check_out(bob, "a1")
    with pytest.raises(NotFound):
        await world.files.edit(bob, "a1", base_version=1, commands=[], summary="x")
    with pytest.raises(Forbidden, match="whole workspace"):
        await world.files.collect(bob)


# ─── collection ──────────────────────────────────────────────────────────────


async def test_collection_keeps_every_blob_a_revision_or_pending_proposal_names(
    world: World,
) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    await world.files.check_in(world.ws, checkout.id, once(FakeApp.file("Terms", "Fees")))
    pending = await world.files.edit(
        world.agent, "a1", base_version=2, commands=[add("x")], summary="x"
    )
    await world.files.upload(
        world.ws,
        WordDocument,
        "old.docx",
        once(FakeApp.file("Old")),
        media_type=DOCX,
        artifact_id="a2",
    )
    await world.ws.commit((await world.ws.get(WordDocument, "a2")).archive())
    orphan = await world.stores.blobs.put(world.scope, "a1", once(b"never committed"), DOCX)
    named = [blob for a in ("a1", "a2") for blob in await _blobs_of(world, a)]
    world.clock.advance(2 * DAY)
    assert await world.files.collect(world.ws) == 1
    assert await world.stores.blobs.get(world.scope, "a1", orphan.sha256) is None
    for artifact_id, blob in named:
        assert await world.stores.blobs.get(world.scope, artifact_id, blob.sha256) is not None
    await world.accept(pending)  # the proposal's bytes were kept for it
    for artifact_id, blob in await _blobs_of(world, "a1"):
        assert await world.stores.blobs.get(world.scope, artifact_id, blob.sha256) is not None


async def _blobs_of(world: World, artifact_id: str) -> list[tuple[str, Blob]]:
    """Every blob any revision of a native file names, read from its manifests' fields."""
    manifests = [WordDocument.model_validate(r.data) for r in await world.ws.revisions(artifact_id)]
    return [
        (artifact_id, blob)
        for m in manifests
        for blob in (m.content, m.text, m.review, m.provenance.commands)
        if blob is not None
    ]


async def test_collection_keeps_what_was_put_lately(world: World) -> None:
    fresh = await world.stores.blobs.put(world.scope, "a1", once(b"about to be committed"), DOCX)
    world.clock.advance(DAY / 2)
    assert await world.files.collect(world.ws) == 0
    assert await world.stores.blobs.get(world.scope, "a1", fresh.sha256) is not None


async def test_a_proposal_accepted_while_collecting_keeps_its_bytes(
    stores: Stores, clock: FakeClock
) -> None:
    accept: list[RespondToProposal] = []

    async def meanwhile(
        tenant: TenantId, workspace: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        """As collection reads the artifacts, after the proposals, Bob accepts the proposal."""
        if accept and access.action == "artifactr:read_artifacts":
            await world.ws.as_actor(BOB).commit(accept.pop())
        return True

    workspaces = Workspaces(InMemoryStorage(clock=clock), authorize=meanwhile)
    world = await _world(stores, clock, workspaces)
    proposed = await world.files.edit(
        world.agent, "a1", base_version=1, commands=[add("Fees")], summary="Fees"
    )
    assert isinstance(proposed, Proposed)
    clock.advance(2 * DAY)
    accept.append(RespondToProposal(proposal_id=proposed.proposal_id, decision="accept"))
    assert await world.files.collect(world.ws) == 0
    assert not accept, "accepted as collection ran"
    assert await world.files.read(world.ws, "a1", part="text") == b"Terms\n\nFees"


def test_an_edit_outlasts_the_apps_deadline(stores: Stores) -> None:
    with pytest.raises(ValueError, match="outlast"):
        NativeFiles(stores.blobs, stores.checkouts, FakeApp(), deadline=45.0)


def test_digests_are_found_wherever_a_blob_is() -> None:
    blob = {"sha256": "a" * 64, "size": 1, "media_type": DOCX}
    nested = {"sha256": "b" * 64, "size": 2, "media_type": "application/json", "extra": blob}
    value = {"ops": [{"value": blob}, {"value": [nested]}], "fingerprint": "c" * 64}
    assert digests(value) == {"a" * 64, "b" * 64}
    assert digests({"sha256": "d" * 64}) == set(), "not a blob without its size and type"
