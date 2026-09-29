"""The resume rule, and the contract between core and a host."""

import pytest

from artifactr.core import (
    PROTOCOL,
    EditArtifact,
    Hello,
    NotLoaded,
    RespondToProposal,
    State,
    TextEdit,
    TextEdits,
    UnsupportedProtocol,
    UserActor,
    ValidationFailed,
    commit,
    needs,
    resume,
)

ALICE = UserActor(id="alice")


class TestResume:
    def test_resumes_after_the_clients_last_seq(self) -> None:
        plan = resume(Hello(protocol=PROTOCOL, resume_after_seq=40), head_seq=57)
        assert (plan.replay_after, plan.reset) == (40, False)

    def test_a_new_client_replays_everything(self) -> None:
        assert resume(Hello(protocol=PROTOCOL), head_seq=57).replay_after == 0

    def test_a_client_ahead_of_the_log_resets(self) -> None:
        plan = resume(Hello(protocol=PROTOCOL, resume_after_seq=90), head_seq=57)
        assert (plan.replay_after, plan.reset) == (0, True)

    def test_a_client_behind_retention_resets(self) -> None:
        plan = resume(
            Hello(protocol=PROTOCOL, resume_after_seq=3), head_seq=57, first_retained_seq=10
        )
        assert (plan.replay_after, plan.reset) == (9, True)

    def test_the_server_owns_the_protocol_version(self) -> None:
        with pytest.raises(UnsupportedProtocol, match=r"speaks artifactr\.v1"):
            resume(Hello(protocol="artifactr.v0"), head_seq=0)
        with pytest.raises(UnsupportedProtocol):
            resume(Hello(protocol="artifactr.v0", from_head=True), head_seq=0)

    def test_a_client_can_start_at_the_head_and_replay_nothing(self) -> None:
        plan = resume(Hello(protocol=PROTOCOL, from_head=True), head_seq=57, first_retained_seq=10)
        assert (plan.replay_after, plan.reset) == (57, False)
        assert resume(Hello(protocol=PROTOCOL, from_head=True), head_seq=0).replay_after == 0

    def test_a_client_cannot_start_at_the_head_and_resume(self) -> None:
        with pytest.raises(ValidationFailed, match="resume_after_seq must be 0"):
            resume(Hello(protocol=PROTOCOL, resume_after_seq=40, from_head=True), head_seq=57)


class TestHostContract:
    def test_needs_reveals_dependencies_in_rounds(self) -> None:
        command = RespondToProposal(proposal_id="p1", decision="reject")
        first = needs(command, actor=ALICE)
        assert (first.proposals, first.artifacts) == (frozenset({"p1"}), frozenset())
        assert not needs(command, actor=ALICE, state=State(proposals={"p1": None}))

    def test_deciding_without_loading_is_a_host_bug(self) -> None:
        command = EditArtifact(
            artifact_id="n1", base_version=1, patch=TextEdits(edits=(TextEdit(old="a", new="b"),))
        )
        with pytest.raises(NotLoaded, match="artifact n1 was not loaded"):
            commit(command, State(), actor=ALICE)
