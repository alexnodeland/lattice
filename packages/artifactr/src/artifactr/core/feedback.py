"""Typed feedback: people's and evaluators' judgements of artifacts, threads, turns and messages.

A feedback type is a Pydantic model that subclasses :class:`Feedback`, registered by name like
an artifact type, and declares the targets it can be given on (ADR-0028)::

    class Helpfulness(Feedback, name="helpfulness", targets={"turn", "thread"}):
        rating: Annotated[int, Field(ge=1, le=5)]
        reason: str | None = None

Feedback is given with the ``give_feedback`` command and recorded as a ``feedback_given``
event, so it is validated, attributed and replayable, and every surface has it. An evaluator's
verdict is feedback too, given by an :class:`~artifactr.core.EvaluatorActor`.
"""

import json
import re
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from artifactr.core.errors import NotFound, ValidationFailed
from artifactr.core.ids import ArtifactId, MessageId, RunId, ThreadId

type TargetKind = Literal["artifact", "thread", "turn", "message"]
"""What feedback can be about: an artifact version, a thread, a turn (a run) or a message."""

TARGET_KINDS: frozenset[TargetKind] = frozenset({"artifact", "thread", "turn", "message"})
"""Every kind of target."""


class ArtifactTarget(BaseModel):
    """Feedback on one version of an artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["artifact"] = "artifact"
    artifact_id: ArtifactId
    version: int = Field(ge=1)


class ThreadTarget(BaseModel):
    """Feedback on a whole thread: the session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["thread"] = "thread"
    thread_id: ThreadId


class TurnTarget(BaseModel):
    """Feedback on the agent's turn: its run, which may span pauses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["turn"] = "turn"
    run_id: RunId


class MessageTarget(BaseModel):
    """Feedback on one message in a thread.

    Messages live only in the log, so the target names the thread they were posted in, and,
    for the agent's messages, the run that posted them (the ``run_id`` of its
    ``message_posted``), which links the feedback to the run's trace.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["message"] = "message"
    message_id: MessageId
    thread_id: ThreadId
    run_id: RunId | None = None


type FeedbackTarget = Annotated[
    ArtifactTarget | ThreadTarget | TurnTarget | MessageTarget, Field(discriminator="kind")
]
"""What a piece of feedback is about, discriminated by ``kind``."""

_registry: dict[str, type["Feedback"]] = {}


class Feedback(BaseModel):
    """Base class for feedback types.

    Subclass it with ordinary Pydantic fields, and declare the targets it applies to with
    ``targets=``. Field types decide how each field is scored in evaluation backends: bounded
    numbers are numeric, ``bool`` is yes or no, ``Literal`` and ``Enum`` are categories, and
    ``str`` is free text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    feedback_type: ClassVar[str]
    """The registered type name, derived from the class name unless given as ``name=``."""

    targets: ClassVar[frozenset[TargetKind]]
    """The kinds of target this type of feedback can be given on."""

    def __init_subclass__(
        cls,
        *,
        name: str | None = None,
        targets: Iterable[TargetKind] | None = None,
        abstract: bool = False,
        **kwargs: Any,
    ) -> None:
        # Consumed in __pydantic_init_subclass__, once the fields exist.
        super().__init_subclass__(**kwargs)

    @classmethod
    def __pydantic_init_subclass__(
        cls,
        *,
        name: str | None = None,
        targets: Iterable[TargetKind] | None = None,
        abstract: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if abstract:
            return
        chosen = frozenset(targets or ())
        if not chosen or not chosen <= TARGET_KINDS:
            raise TypeError(
                f"{cls.__name__} must declare targets from {sorted(TARGET_KINDS)}, "
                "such as targets={'turn'}"
            )
        cls.targets = chosen
        cls.feedback_type = name or _snake_case(cls.__name__)
        _register(cls)


def feedback_types() -> Mapping[str, type[Feedback]]:
    """Return a read-only view of every registered feedback type, by name."""
    return MappingProxyType(_registry)


def get_feedback_type(feedback_type: str) -> type[Feedback]:
    """Return the feedback type registered under a name.

    Raises:
        NotFound: If no feedback type is registered under that name.
    """
    try:
        return _registry[feedback_type]
    except KeyError:
        raise NotFound("feedback type", feedback_type) from None


def load_feedback(
    feedback_type: str,
    target: ArtifactTarget | ThreadTarget | TurnTarget | MessageTarget,
    value: Mapping[str, Any],
) -> Feedback:
    """Validate feedback of a registered type, given on a target.

    Raises:
        NotFound: If no feedback type is registered under that name.
        ValidationFailed: If the type cannot be given on that kind of target, or the value does
            not validate.
    """
    model = get_feedback_type(feedback_type)
    if target.kind not in model.targets:
        allowed = ", ".join(sorted(model.targets))
        raise ValidationFailed(
            f"{feedback_type} feedback is given on {allowed}, not on a {target.kind}", []
        )
    try:
        return model.model_validate(dict(value))
    except ValidationError as error:
        errors: list[JsonValue] = json.loads(error.json(include_url=False))
        raise ValidationFailed(f"invalid {feedback_type} feedback", errors) from error


def _snake_case(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).lower()


def _qualified(feedback_type: type[Feedback]) -> str:
    return f"{feedback_type.__module__}.{feedback_type.__qualname__}"


def _register(feedback_type: type[Feedback]) -> None:
    existing = _registry.get(feedback_type.feedback_type)
    if existing is not None and _qualified(existing) != _qualified(feedback_type):
        raise TypeError(
            f"feedback type name {feedback_type.feedback_type!r} is already registered by "
            f"{_qualified(existing)}; pass name=... to choose another"
        )
    _registry[feedback_type.feedback_type] = feedback_type
