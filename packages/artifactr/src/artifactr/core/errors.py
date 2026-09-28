"""Rejections: the ways a command can fail.

Every rejection has a stable ``code``, which is what the thread protocol sends to clients in a
``command_result`` frame, and a :meth:`Rejection.payload` with its typed details.
"""

from typing import ClassVar

from pydantic import JsonValue


class Rejection(Exception):
    """Base class for every reason core refuses a command."""

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


class VersionConflict(Rejection):
    """The command was based on a version that is no longer current."""

    code: ClassVar[str] = "version_conflict"

    def __init__(self, artifact_id: str, *, base: int, head: int) -> None:
        super().__init__(
            f"artifact {artifact_id} is at version {head}, but the change was based on {base}"
        )
        self.artifact_id = artifact_id
        self.base = base
        self.head = head

    def details(self) -> dict[str, JsonValue]:
        """Return the artifact and both versions."""
        return {"artifact_id": self.artifact_id, "base": self.base, "head": self.head}


class ValidationFailed(Rejection):
    """The resulting data does not validate against the artifact type."""

    code: ClassVar[str] = "validation_failed"

    def __init__(self, message: str, errors: list[JsonValue]) -> None:
        super().__init__(message)
        self.errors = errors

    def details(self) -> dict[str, JsonValue]:
        """Return Pydantic's validation errors."""
        return {"errors": self.errors}


class PatchFailed(Rejection):
    """The patch does not apply to the data."""

    code: ClassVar[str] = "patch_failed"


class NotFound(Rejection):
    """Something the command refers to does not exist."""

    code: ClassVar[str] = "not_found"

    def __init__(self, entity: str, id: str) -> None:
        super().__init__(f"{entity} {id} does not exist")
        self.entity = entity
        self.id = id

    def details(self) -> dict[str, JsonValue]:
        """Return what was missing."""
        return {"entity": self.entity, "id": self.id}


class Forbidden(Rejection):
    """The actor may not perform this command."""

    code: ClassVar[str] = "forbidden"


class InvalidState(Rejection):
    """The command does not apply to the current state, such as answering a finished run."""

    code: ClassVar[str] = "invalid_state"


class UnsupportedProtocol(Rejection):
    """The client asked for a protocol version the server does not speak."""

    code: ClassVar[str] = "unsupported_protocol"
