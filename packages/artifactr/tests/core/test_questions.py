"""The questions ``ask_user`` asks, the answers they take, and what the agent is told."""

from typing import Any

import pytest
from pydantic import JsonValue, ValidationError

from artifactr.core import (
    Answers,
    Question,
    Questions,
    Reply,
    ValidationFailed,
    answer_for_model,
    check_answer,
)

DAY = {
    "question": "Which day suits the launch?",
    "header": "Day",
    "options": [
        {"label": "Monday", "description": "The start of the week"},
        {"label": "Friday", "description": "Before the weekend", "recommended": True},
    ],
}
CHECKS = {
    "question": "Which checks should run?",
    "header": "Checks",
    "options": [{"label": "Lint"}, {"label": "Tests"}, {"label": "Types"}],
    "multiple": True,
    "other": True,
}
ASKED: dict[str, JsonValue] = {"questions": [DAY, CHECKS]}


def test_the_options_an_agent_recommends_come_first() -> None:
    question = Question.model_validate(DAY)
    assert [option.label for option in question.options] == ["Friday", "Monday"]
    assert (question.multiple, question.other) == (False, False)


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"options": [{"label": "Monday"}, {"label": "Monday"}]}, "unique"),
        ({"options": [{"label": "Monday"}]}, "at least 2"),
        ({"header": "A header far too long"}, "at most 16"),
    ],
)
def test_a_question_is_refused_as_the_agent_asks_it(change: dict[str, Any], why: str) -> None:
    with pytest.raises(ValidationError, match=why):
        Question.model_validate({**DAY, **change})


def test_one_to_four_questions_are_asked() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        Questions.model_validate({"questions": []})
    with pytest.raises(ValidationError, match="at most 4"):
        Questions.model_validate({"questions": [DAY] * 5})
    with pytest.raises(ValidationError, match="asked once"):
        Questions.model_validate({"questions": [DAY, DAY]})


def test_choices_and_words_answer_the_questions_in_order() -> None:
    answer: JsonValue = {
        "answers": [{"selected": ["Friday"]}, {"selected": ["Lint"], "other": "Docs"}]
    }
    assert check_answer(ASKED, answer) == Answers.model_validate(answer)
    assert answer_for_model(ASKED, answer) == [
        {"question": "Which day suits the launch?", "selected": ["Friday"]},
        {"question": "Which checks should run?", "selected": ["Lint"], "other": "Docs"},
    ]


def test_a_reply_answers_them_all_in_its_words() -> None:
    reply: JsonValue = {"reply": "Whenever the team is back"}
    assert check_answer(ASKED, reply) == Reply(reply="Whenever the team is back")
    assert answer_for_model(ASKED, reply) == reply


@pytest.mark.parametrize(
    ("checks", "why"),
    [
        ({"selected": ["Lint", "Lint"]}, "'Checks' has an option chosen twice"),
        ({"other": "  "}, "'Checks' has empty words of its own"),
        ({}, "'Checks' is unanswered"),
    ],
)
def test_an_answer_that_does_not_fit_its_question_is_refused(
    checks: dict[str, JsonValue], why: str
) -> None:
    answer: JsonValue = {"answers": [{"selected": ["Friday"]}, checks]}
    with pytest.raises(ValidationFailed, match=why) as refused:
        check_answer(ASKED, answer)
    assert refused.value.errors == [{"type": "value_error", "loc": ["answers", 1], "msg": why}]


def test_a_question_asked_in_words_before_is_answered_only_with_a_reply() -> None:
    asked_before: dict[str, JsonValue] = {"question": "Which day?", "choices": ["Monday"]}
    assert check_answer(asked_before, {"reply": "Monday"}) == Reply(reply="Monday")
    with pytest.raises(ValidationFailed, match="asked no questions to choose from") as refused:
        check_answer(asked_before, {"answers": [{"selected": ["Monday"]}]})
    assert refused.value.errors, "pydantic's errors, as the wire carries them"
