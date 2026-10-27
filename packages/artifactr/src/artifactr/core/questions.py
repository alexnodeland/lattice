"""The questions the agent asks through ``ask_user``, and how they are answered (ADR-0084).

``ask_user`` asks one to four questions at once. Each has a short header, two to four options,
each a label and what it means, and says whether several may be chosen and whether the person may
answer in their own words instead. Options the agent recommends come first.

A request is answered once, with one of two shapes, which :func:`check_answer` holds to the
request's questions as the answer is committed:

- :class:`Answers`: what was chosen for each question, in order, and any words of the person's own.
- :class:`Reply`: a message posted in the thread while the questions were open, in its words. It
  answers a request recorded before ``ask_user`` asked questions, too, which asked one in words.

:func:`answer_for_model` is what the agent's tool call returns: each question beside its answer.
"""

import json
from typing import Annotated, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from artifactr.core.errors import ValidationFailed

ASK_USER: Final = "ask_user"
"""The agent's tool that asks the people in its thread questions and waits for their answers."""

OTHER: Final = "other"
"""The choice clients draw for a person's own words, which no option may be labelled."""


class Option(BaseModel):
    """One answer a question offers."""

    model_config = ConfigDict(frozen=True)

    label: Annotated[str, Field(min_length=1, max_length=60)]
    """The words a person chooses, unique in its question."""
    description: Annotated[str, Field(max_length=200)] = ""
    """What choosing it means, in a sentence."""
    recommended: bool = False
    """Whether the agent recommends it: recommended options come first."""


class Question(BaseModel):
    """One question, and the options it offers."""

    model_config = ConfigDict(frozen=True)

    question: Annotated[str, Field(min_length=1, max_length=500)]
    """The question, in full."""
    header: Annotated[str, Field(min_length=1, max_length=16)]
    """A word or two that names it, such as ``Due date``."""
    options: Annotated[tuple[Option, ...], Field(min_length=2, max_length=4)]
    multiple: bool = False
    """Whether more than one option may be chosen."""
    other: bool = False
    """Whether the person may answer in their own words instead of, or beside, the options."""

    @field_validator("options")
    @classmethod
    def _distinct_and_recommended_first(cls, options: tuple[Option, ...]) -> tuple[Option, ...]:
        labels = [option.label for option in options]
        if len(set(labels)) != len(labels):
            raise ValueError("each option's label must be unique in its question")
        if any(label.strip().casefold() == OTHER for label in labels):
            raise ValueError("'Other' is offered by setting other, not as an option")
        return tuple(sorted(options, key=lambda option: not option.recommended))


class Questions(BaseModel):
    """What ``ask_user`` asks: its arguments."""

    model_config = ConfigDict(frozen=True)

    questions: Annotated[tuple[Question, ...], Field(min_length=1, max_length=4)]

    @field_validator("questions")
    @classmethod
    def _distinct(cls, questions: tuple[Question, ...]) -> tuple[Question, ...]:
        if len({question.question for question in questions}) != len(questions):
            raise ValueError("each question is asked once")
        return questions


class Chosen(BaseModel):
    """The answer to one question: the labels chosen, and any words of the person's own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selected: tuple[str, ...] = ()
    other: Annotated[str, Field(max_length=2000)] | None = None


class Answers(BaseModel):
    """An answer to every question a request asked, in the order they were asked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answers: tuple[Chosen, ...]


class Reply(BaseModel):
    """A message that answered the questions in its own words, instead of choosing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reply: Annotated[str, Field(min_length=1, max_length=20000, pattern=r"\S")]


_ANSWER = TypeAdapter[Answers | Reply](Answers | Reply)


def check_answer(args: dict[str, JsonValue], answer: JsonValue) -> Answers | Reply:
    """Hold an answer to the questions an ``ask_user`` request asked.

    A reply answers any request, one recorded before ``ask_user`` asked questions among them.
    Answers answer each question, in order. A single choice has exactly one answer: a label, or,
    where the question allows them, the person's own words. Several choices have at least one
    label or words. Labels are the question's own, each chosen once.

    Raises:
        ValidationFailed: If the answer is neither, or doesn't fit the questions.
    """
    try:
        given = _ANSWER.validate_python(answer)
    except ValidationError as error:
        raise _invalid("questions are answered with answers or a reply", error) from error
    if isinstance(given, Reply):
        return given
    try:
        asked = Questions.model_validate(args)
    except ValidationError as error:
        raise _invalid(
            "this request asked no questions to choose from: reply to it", error
        ) from error
    if len(given.answers) != len(asked.questions):
        asked_answered = f"{len(asked.questions)} asked, {len(given.answers)} answered"
        raise _refused(f"each question needs its answer: {asked_answered}", [])
    for at, (question, chosen) in enumerate(zip(asked.questions, given.answers, strict=True)):
        _check_one(at, question, chosen)
    return given


def answer_for_model(args: dict[str, JsonValue], answer: JsonValue) -> JsonValue:
    """What the agent's ``ask_user`` call returns: each question beside how it was answered.

    Core holds an answer only as it is committed. One committed before it held them, such as a
    string answering a question asked before ``ask_user`` took options, is passed through as it
    was, so its run still resumes.
    """
    try:
        given = check_answer(args, answer)
    except ValidationFailed:
        return answer
    if isinstance(given, Reply):
        return {"reply": given.reply}
    asked = Questions.model_validate(args)
    return [
        {
            "question": question.question,
            "selected": list(chosen.selected),
            **({"other": chosen.other} if chosen.other is not None else {}),
        }
        for question, chosen in zip(asked.questions, given.answers, strict=True)
    ]


def _check_one(at: int, question: Question, chosen: Chosen) -> None:
    """Hold the answer to the question at index ``at``."""
    loc: list[JsonValue] = ["answers", at]
    labels = {option.label for option in question.options}
    if unknown := [label for label in chosen.selected if label not in labels]:
        raise _refused(f"{question.header!r} offers no option {unknown[0]!r}", loc)
    if len(set(chosen.selected)) != len(chosen.selected):
        raise _refused(f"{question.header!r} has an option chosen twice", loc)
    if chosen.other is not None:
        if not question.other:
            raise _refused(f"{question.header!r} is answered only with its options", loc)
        if not chosen.other.strip():
            raise _refused(f"{question.header!r} has empty words of its own", loc)
    given = len(chosen.selected) + (chosen.other is not None)
    if given == 0:
        raise _refused(f"{question.header!r} is unanswered", loc)
    if given > 1 and not question.multiple:
        raise _refused(f"{question.header!r} takes one answer", loc)


def _refused(message: str, loc: list[JsonValue]) -> ValidationFailed:
    return ValidationFailed(message, [{"type": "value_error", "loc": loc, "msg": message}])


def _invalid(message: str, error: ValidationError) -> ValidationFailed:
    errors: list[JsonValue] = json.loads(error.json(include_url=False))
    return ValidationFailed(message, errors)
