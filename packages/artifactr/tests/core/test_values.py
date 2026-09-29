"""Actors, identifiers, patches, rejections and state helpers."""

import pytest
from pydantic import TypeAdapter

from artifactr.core import (
    Actor,
    AgentActor,
    DeferredAnswer,
    DeferredRequest,
    ExternalAgentActor,
    JsonPatch,
    Needs,
    NotFound,
    PatchFailed,
    Run,
    SystemActor,
    TextEdit,
    TextEdits,
    UserActor,
    ValidationFailed,
    VersionConflict,
    apply_patch,
    describe_patch,
    diff,
    is_agent,
    new_artifact_id,
    new_message_id,
    new_proposal_id,
    new_run_id,
    new_thread_id,
    same_participant,
)


class TestActors:
    def test_participants_and_names(self) -> None:
        cases: list[tuple[Actor, str, str]] = [
            (UserActor(id="u1"), "user:u1", "u1"),
            (UserActor(id="u1", name="Alice"), "user:u1", "Alice"),
            (AgentActor(thread_id="t1", run_id="r1"), "agent:t1", "assistant"),
            (ExternalAgentActor(client_id="cc"), "external_agent:cc", "cc"),
            (
                ExternalAgentActor(client_id="cc", name="Claude Code"),
                "external_agent:cc",
                "Claude Code",
            ),
            (SystemActor(), "system:system", "system"),
        ]
        for actor, participant, name in cases:
            assert (actor.participant, actor.display_name) == (participant, name)

    def test_every_run_of_a_threads_agent_is_one_participant(self) -> None:
        assert same_participant(AgentActor(thread_id="t1", run_id="r1"), AgentActor(thread_id="t1"))
        assert not same_participant(AgentActor(thread_id="t1"), AgentActor(thread_id="t2"))
        assert not same_participant(UserActor(id="x"), ExternalAgentActor(client_id="x"))

    def test_agents_are_subject_to_write_policies(self) -> None:
        assert is_agent(AgentActor(thread_id="t1"))
        assert is_agent(ExternalAgentActor(client_id="c"))
        assert not is_agent(UserActor(id="u"))
        assert not is_agent(SystemActor())

    def test_actors_are_discriminated_by_kind(self) -> None:
        actor = TypeAdapter[Actor](Actor).validate_python({"kind": "system", "name": "cron"})
        assert actor == SystemActor(name="cron")


def test_identifier_factories_are_prefixed_and_unique() -> None:
    for factory, prefix in [
        (new_artifact_id, "art_"),
        (new_thread_id, "thr_"),
        (new_run_id, "run_"),
        (new_proposal_id, "prp_"),
        (new_message_id, "msg_"),
    ]:
        first, second = factory(), factory()
        assert first.startswith(prefix)
        assert first != second


class TestPatches:
    def test_an_empty_anchor_writes_an_empty_field(self) -> None:
        edits = TextEdits(edits=(TextEdit(old="", new="Hello"),))
        assert apply_patch({"text": ""}, edits) == {"text": "Hello"}

    def test_an_empty_anchor_cannot_overwrite_text(self) -> None:
        edits = TextEdits(edits=(TextEdit(old="", new="Hello"),))
        with pytest.raises(PatchFailed, match="only allowed when the text is empty"):
            apply_patch({"text": "existing"}, edits)

    def test_an_ambiguous_anchor_fails(self) -> None:
        edits = TextEdits(edits=(TextEdit(old="x", new="y"),))
        with pytest.raises(PatchFailed, match="ambiguous: it occurs 2 times"):
            apply_patch({"text": "x then x"}, edits)

    def test_long_anchors_are_shortened_in_messages(self) -> None:
        edits = TextEdits(edits=(TextEdit(old="x" * 100, new="y"),))
        with pytest.raises(PatchFailed) as failed:
            apply_patch({"text": "short"}, edits)
        assert "x" * 59 + "…" in failed.value.message

    def test_edits_apply_in_sequence(self) -> None:
        edits = TextEdits(edits=(TextEdit(old="one", new="two"), TextEdit(old="two", new="three")))
        assert apply_patch({"text": "one"}, edits) == {"text": "three"}

    def test_diff_round_trips(self) -> None:
        before = {"a": 1, "items": {"t1": {"done": False}}}
        after = {"a": 1, "items": {"t1": {"done": True}, "t2": {"done": False}}}
        assert apply_patch(before, diff(before, after)) == after

    def test_descriptions(self) -> None:
        one = TextEdits(edits=(TextEdit(old="a", new="b"),))
        two = TextEdits(
            field="body", edits=(TextEdit(old="a", new="b"), TextEdit(old="c", new="d"))
        )
        many = JsonPatch(ops=tuple({"op": "add", "path": f"/k{i}", "value": i} for i in range(5)))
        assert describe_patch(one) == "edited text (1 replacement)"
        assert describe_patch(two) == "edited body (2 replacements)"
        assert describe_patch(many) == "add /k0; add /k1; add /k2; and 2 more"


class TestRejections:
    def test_payloads_carry_code_message_and_details(self) -> None:
        conflict = VersionConflict("a1", base=1, head=2)
        assert conflict.payload() == {
            "type": "version_conflict",
            "message": "artifact a1 is at version 2, but the change was based on 1",
            "artifact_id": "a1",
            "base": 1,
            "head": 2,
        }
        assert NotFound("run", "r1").payload()["entity"] == "run"
        assert ValidationFailed("bad", [{"loc": ["x"]}]).payload()["errors"] == [{"loc": ["x"]}]
        assert PatchFailed("nope").payload() == {"type": "patch_failed", "message": "nope"}


class TestState:
    def test_needs_is_falsy_when_empty(self) -> None:
        assert not Needs()
        assert Needs(runs=frozenset({"r1"}))
        assert Needs(messages=frozenset({"m1"}))

    def test_a_paused_run_is_ready_once_every_request_is_answered(self) -> None:
        requests = (
            DeferredRequest(tool_call_id="a", tool_name="ask", kind="question"),
            DeferredRequest(tool_call_id="b", tool_name="delete", kind="approval"),
        )
        paused = Run(id="r1", thread_id="t1", status="paused", pending=requests)
        assert not paused.all_answered
        partly = paused.model_copy(update={"answers": {"a": DeferredAnswer(answer="yes")}})
        assert not partly.all_answered
        done = partly.model_copy(
            update={"answers": {**partly.answers, "b": DeferredAnswer(approved=True)}}
        )
        assert done.all_answered
        assert not done.model_copy(update={"status": "running"}).all_answered
