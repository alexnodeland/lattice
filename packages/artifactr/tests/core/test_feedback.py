"""Feedback types: registration, their targets, and validating feedback."""

from typing import Any

import pytest

from artifactr.core import (
    TARGET_KINDS,
    ArtifactTarget,
    EvaluatorActor,
    Feedback,
    NotFound,
    ThreadTarget,
    TurnTarget,
    ValidationFailed,
    feedback_types,
    get_feedback_type,
    load_feedback,
    same_participant,
)
from tests.artifact_types import Accuracy, Helpfulness


def test_types_register_by_name_with_their_targets() -> None:
    class ToneOfVoice(Feedback, targets={"message"}):
        friendly: bool

    assert ToneOfVoice.feedback_type == "tone_of_voice"
    assert ToneOfVoice.targets == {"message"}
    assert feedback_types()["tone_of_voice"] is ToneOfVoice
    assert get_feedback_type("helpfulness") is Helpfulness
    assert Accuracy.targets <= TARGET_KINDS


def test_abstract_bases_are_not_registered() -> None:
    class Scored(Feedback, abstract=True):
        score: int

    class Clarity(Scored, name="clarity_score", targets={"turn"}):
        pass

    assert "scored" not in feedback_types()
    assert Clarity.feedback_type == "clarity_score"
    assert list(Clarity.model_fields) == ["score"]


def test_a_type_must_declare_known_targets() -> None:
    with pytest.raises(TypeError, match="must declare targets"):

        class Untargeted(Feedback):
            pass

    unknown: Any = {"workspace"}
    with pytest.raises(TypeError, match="must declare targets"):

        class Misplaced(Feedback, targets=unknown):
            pass


def test_a_name_cannot_be_registered_twice() -> None:
    with pytest.raises(TypeError, match="already registered"):

        class Imposter(Feedback, name="helpfulness", targets={"turn"}):
            pass


def test_loading_validates_the_type_the_target_and_the_value() -> None:
    feedback = load_feedback("helpfulness", TurnTarget(run_id="run_1"), {"rating": 5})
    assert feedback == Helpfulness(rating=5)
    with pytest.raises(NotFound):
        load_feedback("vibes", ThreadTarget(thread_id="thr_1"), {})
    with pytest.raises(ValidationFailed, match="given on artifact, not on a turn"):
        load_feedback("accuracy", TurnTarget(run_id="run_1"), {"correct": True})
    with pytest.raises(ValidationFailed) as invalid:
        load_feedback("accuracy", ArtifactTarget(artifact_id="a", version=1), {"correct": "maybe"})
    assert invalid.value.errors


def test_an_evaluator_is_one_participant_per_version() -> None:
    v3 = EvaluatorActor(name="judge", version="v3")
    assert (v3.participant, v3.display_name) == ("evaluator:judge@v3", "judge@v3")
    assert not same_participant(v3, EvaluatorActor(name="judge", version="v4"))
