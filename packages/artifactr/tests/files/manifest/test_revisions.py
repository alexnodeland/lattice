"""A revision is JSON Patch that tests the digest it was made from (artifactr ADR-0072)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from artifactr.core import (
    AgentActor,
    JsonPatch,
    PatchFailed,
    ProposeChange,
    RespondToProposal,
    UserActor,
    apply_patch,
)
from artifactr.workspace import InMemoryStorage, Workspaces
from artifactr_files.manifest import REVISED, Provenance, WordDocument, revise
from tests.files_of import digest, document

SEEDS = st.text(min_size=1, max_size=8)
ALICE = UserActor(id="alice", name="Alice")


@given(head=SEEDS, after=SEEDS, outline=st.text(max_size=20))
def test_a_revision_of_its_base_gives_the_new_manifest(head: str, after: str, outline: str) -> None:
    base = document(head)
    new = document(after, name="ignored.docx", outline=outline)
    edit = revise("a1", new, base_version=1, tested=base.content.sha256, summary="s")
    patched = apply_patch(base.to_json(), edit.patch)
    assert patched == {**new.to_json(), "name": base.name}, "everything but the name"


@given(head=SEEDS, tested=SEEDS, after=SEEDS)
def test_a_revision_of_another_base_does_not_apply(head: str, tested: str, after: str) -> None:
    base = document(head)
    edit = revise("a1", document(after), base_version=1, tested=digest(tested), summary="s")
    if digest(tested) == base.content.sha256:
        apply_patch(base.to_json(), edit.patch)
    else:
        with pytest.raises(PatchFailed):
            apply_patch(base.to_json(), edit.patch)


def test_a_revision_tests_first_then_replaces_all_but_the_name() -> None:
    edit = revise("a1", document("b"), base_version=3, tested=digest("a"), summary="Added terms")
    assert isinstance(edit.patch, JsonPatch)
    first, *rest = edit.patch.ops
    assert first == {"op": "test", "path": "/content/sha256", "value": digest("a")}
    assert [op["path"] for op in rest] == [f"/{name}" for name in REVISED]
    assert [op["op"] for op in rest] == ["replace"] * len(REVISED)
    assert (edit.base_version, edit.summary) == (3, "Added terms")


async def test_accepting_a_stale_proposal_fails_and_one_made_at_the_head_applies() -> None:
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await ws.create(document("v1"), artifact_id="a1")
    agent = ws.as_actor(AgentActor(thread_id="t1", run_id="r1"))

    def proposal(seed: str, version: int, tested: str) -> ProposeChange:
        after = document(seed).model_copy(update={"provenance": Provenance(source="commands")})
        return ProposeChange(
            change=revise("a1", after, base_version=version, tested=tested, summary=seed)
        )

    first = await agent.commit(proposal("first", 1, digest("v1")))
    stale = await agent.commit(proposal("second", 1, digest("v1")))
    await ws.commit(RespondToProposal(proposal_id=first.proposal_id, decision="accept"))
    with pytest.raises(PatchFailed, match="not equal to tested value"):
        await ws.commit(RespondToProposal(proposal_id=stale.proposal_id, decision="accept"))
    assert (await ws.get(WordDocument, "a1")).data.content.sha256 == digest("first")
    rebuilt = await agent.commit(proposal("second", 2, digest("first")))
    await ws.commit(RespondToProposal(proposal_id=rebuilt.proposal_id, decision="accept"))
    head = await ws.get(WordDocument, "a1")
    assert (head.version, head.data.content.sha256) == (3, digest("second"))
