"""The bridged types, and what the default set and the application's projections make of each
envelope."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

import artifactr.core as a
from reflexr.core import dump_event, load_event
from relayr.events import (
    BRIDGED,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    FeedbackGiven,
    MessagePosted,
    Projections,
    ProposalCreated,
    ProposalResolved,
    TurnEnded,
    bridged,
)
from tests.app_types import Deployed, TimelineChanged

ALICE = a.UserActor(id="alice")
AGENT = a.AgentActor(thread_id="thr_1", run_id="run_1")
PATCH = a.JsonPatch(ops=({"op": "replace", "path": "/title", "value": "Deploys"},))
CREATE = a.CreateArtifact(artifact_id="art_1", kind="note", data={"title": "x"})


def envelope(
    event: Any, *, actor: a.Actor = ALICE, thread_id: str | None = None, run_id: str | None = None
) -> a.Envelope:
    return a.Envelope.model_validate(
        {
            "seq": 1,
            "id": "evt_1",
            "ts": datetime(2026, 10, 12, tzinfo=UTC),
            "workspace_id": "prod",
            "thread_id": thread_id,
            "run_id": run_id,
            "actor": actor,
            "event": event,
        }
    )


def test_every_bridged_type_is_in_the_artifactr_namespace() -> None:
    assert [t.event_type for t in BRIDGED] == [
        "artifactr:message_posted",
        "artifactr:artifact_created",
        "artifactr:artifact_changed",
        "artifactr:artifact_archived",
        "artifactr:proposal_created",
        "artifactr:proposal_resolved",
        "artifactr:turn_ended",
        "artifactr:feedback_given",
    ]


DEFAULT_SET = [
    pytest.param(
        envelope(
            a.MessagePosted(thread_id="thr_1", message_id="msg_1", content="hi", kind="notice"),
            thread_id="thr_1",
        ),
        MessagePosted(
            author=ALICE, thread_id="thr_1", message_id="msg_1", content="hi", kind="notice"
        ),
        id="message_posted",
    ),
    pytest.param(
        envelope(
            a.ArtifactCreated(artifact_id="art_1", kind="note", version=1, data={"title": "x"}),
            actor=AGENT,
            thread_id="thr_1",
            run_id="run_1",
        ),
        ArtifactCreated(
            author=AGENT,
            thread_id="thr_1",
            turn_id="run_1",
            artifact_id="art_1",
            kind="note",
            version=1,
            data={"title": "x"},
        ),
        id="artifact_created",
    ),
    pytest.param(
        envelope(
            a.ArtifactChanged(
                artifact_id="art_1",
                kind="note",
                version=2,
                patch=PATCH,
                summary="retitled",
                proposal_id="prp_1",
            )
        ),
        ArtifactChanged(
            author=ALICE,
            artifact_id="art_1",
            kind="note",
            version=2,
            summary="retitled",
            patch=PATCH,
            proposal_id="prp_1",
        ),
        id="artifact_changed",
    ),
    pytest.param(
        envelope(a.ArtifactArchived(artifact_id="art_1", kind="note", version=3)),
        ArtifactArchived(author=ALICE, artifact_id="art_1", kind="note", version=3),
        id="artifact_archived",
    ),
    pytest.param(
        envelope(
            a.ProposalCreated(proposal_id="prp_1", change=CREATE, rationale="why"), actor=AGENT
        ),
        ProposalCreated(
            author=AGENT, proposal_id="prp_1", proposed_by=AGENT, change=CREATE, rationale="why"
        ),
        id="proposal_created",
    ),
    pytest.param(
        envelope(
            a.ProposalResolved(
                proposal_id="prp_1",
                decision="accept",
                proposed_by=AGENT,
                artifact_id="art_1",
                changes=PATCH,
                version=1,
            )
        ),
        ProposalResolved(
            author=ALICE,
            proposal_id="prp_1",
            proposed_by=AGENT,
            decision="accept",
            artifact_id="art_1",
            changes=PATCH,
            version=1,
        ),
        id="proposal_resolved",
    ),
    pytest.param(
        envelope(
            a.RunEnded(run_id="run_1", thread_id="thr_1", status="failed", reason="abandoned"),
            actor=AGENT,
            thread_id="thr_1",
            run_id="run_1",
        ),
        TurnEnded(
            author=AGENT, thread_id="thr_1", turn_id="run_1", status="failed", reason="abandoned"
        ),
        id="turn_ended",
    ),
    pytest.param(
        envelope(
            a.FeedbackGiven(
                feedback_type="helpfulness",
                target=a.ThreadTarget(thread_id="thr_1"),
                value={"rating": 4},
                thread_id="thr_1",
            ),
            thread_id="thr_1",
        ),
        FeedbackGiven(
            author=ALICE,
            thread_id="thr_1",
            feedback_type="helpfulness",
            target=a.ThreadTarget(thread_id="thr_1"),
            value={"rating": 4},
        ),
        id="feedback_given",
    ),
]


@pytest.mark.parametrize(("given", "expected"), DEFAULT_SET)
def test_the_default_set_bridges_each_of_its_events(given: a.Envelope, expected: Any) -> None:
    assert bridged(given) == expected
    assert Projections().project(given) == expected


@pytest.mark.parametrize(("given", "expected"), DEFAULT_SET)
def test_a_bridged_event_round_trips_as_reflexr_stores_it(given: a.Envelope, expected: Any) -> None:
    assert load_event(dump_event(expected)) == expected


@pytest.mark.parametrize(
    "event",
    [
        a.ThreadCreated(thread_id="thr_1", title="t"),
        a.FocusChanged(thread_id="thr_1", artifact_ids=()),
        a.RunStarted(run_id="run_1", thread_id="thr_1"),
        a.ToolCalled(run_id="run_1", thread_id="thr_1", tool_call_id="c", tool_name="t"),
        a.AppEvent(name="deploy", data={"service": "api"}),
    ],
)
def test_the_default_set_leaves_the_rest_in_artifactr(event: Any) -> None:
    assert bridged(envelope(event)) is None


def deployed(given: a.Envelope) -> Deployed:
    assert isinstance(given.event, a.AppEvent)
    return Deployed.model_validate(given.event.data)


def timeline(given: a.Envelope) -> TimelineChanged | None:
    match given.event:
        case a.ArtifactChanged(version=version):
            return TimelineChanged(entries=version)
        case _:
            return None


PROJECTIONS = Projections(app_events={"deploy": deployed}, artifacts={"timeline": timeline})


def test_an_app_event_is_bridged_by_its_projection() -> None:
    given = envelope(a.AppEvent(name="deploy", data={"service": "api"}))
    assert PROJECTIONS.project(given) == Deployed(service="api")
    assert PROJECTIONS.project(envelope(a.AppEvent(name="other"))) is None


def test_an_invalid_app_event_raises() -> None:
    with pytest.raises(ValidationError):
        PROJECTIONS.project(envelope(a.AppEvent(name="deploy", data={"region": "eu"})))


def test_an_artifact_kinds_projection_replaces_the_default_set() -> None:
    changed = a.ArtifactChanged(
        artifact_id="art_1", kind="timeline", version=4, patch=PATCH, summary="added"
    )
    created = a.ArtifactCreated(artifact_id="art_1", kind="timeline", version=1, data={})
    assert PROJECTIONS.project(envelope(changed)) == TimelineChanged(entries=4)
    assert PROJECTIONS.project(envelope(created)) is None
    other = changed.model_copy(update={"kind": "note"})
    assert isinstance(PROJECTIONS.project(envelope(other)), ArtifactChanged)


def test_a_proposal_on_a_projected_kind_is_bridged_as_the_default_sets() -> None:
    change = a.CreateArtifact(artifact_id="art_1", kind="timeline", data={})
    proposed = envelope(a.ProposalCreated(proposal_id="prp_1", change=change), actor=AGENT)
    assert isinstance(PROJECTIONS.project(proposed), ProposalCreated)
