"""Rejections: the ways a command can fail, and the error for an invalid rule.

Every rejection has a stable ``code``, which is what the stream protocol sends to clients in a
``command_result`` frame, and a :meth:`Rejection.payload` with its typed details.
"""

from collections.abc import Iterable
from typing import ClassVar, Self, override

from pydantic import JsonValue


class Rejection(Exception):
    """Base class for every reason reflexr refuses a command."""

    code: ClassVar[str] = "rejected"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def details(self) -> dict[str, JsonValue]:
        """Return the rejection's typed fields; subclasses extend this."""
        return {}

    def payload(self) -> dict[str, JsonValue]:
        """Return the rejection as JSON-compatible data for the wire."""
        return {"type": self.code, "message": self.message, **self.details()}


class NotFound(Rejection):
    """Something the command refers to does not exist."""

    code: ClassVar[str] = "not_found"

    def __init__(self, entity: str, id: str) -> None:
        super().__init__(f"{entity} {id} does not exist")
        self.entity = entity
        self.id = id

    @override
    def details(self) -> dict[str, JsonValue]:
        """Return what was missing."""
        return {"entity": self.entity, "id": self.id}


class InvalidState(Rejection):
    """The command does not apply to the current state, such as retrying a finished run."""

    code: ClassVar[str] = "invalid_state"


class ValidationFailed(Rejection):
    """The command's data does not validate, such as an event that does not match its type."""

    code: ClassVar[str] = "validation_failed"

    def __init__(self, message: str, errors: list[JsonValue]) -> None:
        super().__init__(message)
        self.errors = errors

    @override
    def details(self) -> dict[str, JsonValue]:
        """Return Pydantic's validation errors."""
        return {"errors": self.errors}


class Forbidden(Rejection):
    """The actor may not perform the command."""

    code: ClassVar[str] = "forbidden"


class DepthExceeded(Rejection):
    """An event would extend a causal chain beyond the workspace's limit."""

    code: ClassVar[str] = "depth_exceeded"

    def __init__(self, depth: int, limit: int) -> None:
        super().__init__(
            f"the event would be at causation depth {depth}, beyond the limit of {limit}"
        )
        self.depth = depth
        self.limit = limit

    @override
    def details(self) -> dict[str, JsonValue]:
        """Return the depth and the limit."""
        return {"depth": self.depth, "limit": self.limit}


class UnsupportedProtocol(Rejection):
    """The client asked for a protocol version this server does not speak."""

    code: ClassVar[str] = "unsupported_protocol"


class Problem(str):
    """One thing wrong with a rule: its message, as a string.

    It carries the rest as Pydantic reports a field's error, so a client can name the field
    without reading the message. A problem found in a filter, or in the rule's size, names no
    field. Two problems are equal if their messages are.
    """

    __slots__ = ("loc", "type")

    loc: tuple[str | int, ...]
    """The path to the field within the rule: names, and the numbers of a list's items. A
    problem that belongs to no field, such as a filter's unknown event type, has none."""

    type: str
    """What is wrong. Pydantic's own name where it has one (``missing``, ``string_too_long``,
    ``less_than_equal``, or a params field's); reflexr's own for the rest: ``not_allowed``,
    ``too_large`` (a size) and ``unknown`` (a name that is not registered)."""

    def __new__(cls, msg: str, type: str, loc: Iterable[str | int] = ()) -> Self:
        """Return a problem with its message, type and path."""
        problem = super().__new__(cls, msg)
        problem.type = type
        problem.loc = tuple(loc)
        return problem

    @override
    def __reduce__(self) -> tuple[object, ...]:
        """Return how copying and pickling rebuild a problem: from its message, type and path."""
        return type(self), (str(self), self.type, self.loc)

    def error(self, *within: str) -> dict[str, JsonValue]:
        """Return the problem as a Pydantic error.

        Args:
            within: Where the rule is in the command, such as ``rule``, which a path to a field
                starts with, as Pydantic's errors for a command do. A problem that names no
                field has an empty ``loc``.
        """
        loc = [*within, *self.loc] if self.loc else []
        return {"loc": list(loc), "msg": str(self), "type": self.type}


class InvalidRule(ValueError):
    """A rule refers to event types, fields, predicates or actions that do not exist.

    Raised when rules are registered, so a mistake fails at startup rather than silently never
    matching.
    """

    def __init__(self, rule: str, problems: list[Problem]) -> None:
        super().__init__(f"rule {rule!r} is invalid: " + "; ".join(problems))
        self.rule = rule
        self.problems = problems
