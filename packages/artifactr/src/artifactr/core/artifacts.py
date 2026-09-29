"""Artifact types, their registry, and versioned instances.

An artifact type is a Pydantic model that subclasses :class:`Artifact` (ADR-0003). Defining
the class registers it, under a name derived from the class name::

    class ReleaseNotes(MarkdownArtifact):  # registered as "release_notes"
        pass


    class Plan(Artifact, name="plan"):  # an explicit name
        write_policy: ClassVar[WritePolicy] = "propose"
        tasks: dict[str, Task] = {}

Pass ``abstract=True`` for intermediate base classes that should not be registered.
"""

import json
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializeAsAny,
    ValidationError,
    computed_field,
)

from artifactr.core.actors import Actor
from artifactr.core.commands import ArchiveArtifact, CreateArtifact, EditArtifact
from artifactr.core.errors import NotFound, ValidationFailed
from artifactr.core.ids import ArtifactId, ThreadId, new_artifact_id
from artifactr.core.patches import TextEdit, TextEdits, diff

WritePolicy = Literal["direct", "propose"]
"""How an artifact type accepts agents' changes: applied directly, or as proposals."""

_registry: dict[str, type["Artifact"]] = {}


class Artifact(BaseModel):
    """Base class for artifact types.

    Subclass it with ordinary Pydantic fields. Override :meth:`render_for_agent` to control
    what the agent sees, and :meth:`describe_change` to summarize changes in your own words.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    kind: ClassVar[str]
    """The registered type name, derived from the class name unless given as ``name=``."""

    write_policy: ClassVar[WritePolicy] = "direct"
    """Whether agents change this type directly or through proposals."""

    def __init_subclass__(
        cls, *, name: str | None = None, abstract: bool = False, **kwargs: Any
    ) -> None:
        # The class arguments are consumed in __pydantic_init_subclass__, which runs once the
        # fields exist; they must not reach object.__init_subclass__.
        super().__init_subclass__(**kwargs)

    @classmethod
    def __pydantic_init_subclass__(
        cls, *, name: str | None = None, abstract: bool = False, **kwargs: Any
    ) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not abstract:
            cls.kind = name or _snake_case(cls.__name__)
            _register(cls)

    def render_for_agent(self) -> str:
        """Return the text the agent sees for this artifact. Defaults to indented JSON."""
        return self.model_dump_json(indent=2)

    def describe_change(self, before: Any) -> str | None:
        """Summarize the change from ``before`` to this state, or return None.

        ``before`` is always an instance of the same type. Annotate it as ``Self`` when you
        override this method; the base annotation is ``Any`` only so that overrides type-check.
        When this returns None, the summary is generated from the patch.
        """

    def to_json(self) -> dict[str, JsonValue]:
        """Return the artifact's data as JSON-compatible values."""
        return self.model_dump(mode="json")


class MarkdownArtifact(Artifact, abstract=True):
    """An artifact whose content is one Markdown ``text`` field.

    It is edited with anchored text replacements (:class:`TextEdits`) as well as JSON Patch.
    """

    text: str = ""

    def render_for_agent(self) -> str:
        """Return the Markdown text."""
        return self.text


class Versioned[A: Artifact](BaseModel):
    """A stored artifact: its data plus identity, version and last author."""

    model_config = ConfigDict(frozen=True)

    id: ArtifactId
    version: int = Field(ge=1)
    data: SerializeAsAny[A]
    updated_by: Actor
    archived: bool = False

    @computed_field
    @property
    def kind(self) -> str:
        """The artifact's registered type name. Serialized, so readers can tell types apart."""
        return self.data.kind

    def edit(
        self,
        change: Callable[[A], object],
        *,
        summary: str | None = None,
        thread_id: ThreadId | None = None,
    ) -> EditArtifact:
        """Build an edit command by mutating a copy of the data.

        ``change`` receives a deep copy of the data and mutates it in place; its return value
        is ignored. The difference becomes a JSON Patch based on this version.
        """
        draft = self.data.model_copy(deep=True)
        change(draft)
        return EditArtifact(
            artifact_id=self.id,
            base_version=self.version,
            patch=diff(self.data.to_json(), draft.to_json()),
            summary=summary,
            thread_id=thread_id,
        )

    def edit_text(
        self,
        old: str,
        new: str,
        *,
        field: str = "text",
        summary: str | None = None,
        thread_id: ThreadId | None = None,
    ) -> EditArtifact:
        """Build an edit command that replaces the unique occurrence of ``old`` with ``new``."""
        return EditArtifact(
            artifact_id=self.id,
            base_version=self.version,
            patch=TextEdits(field=field, edits=(TextEdit(old=old, new=new),)),
            summary=summary,
            thread_id=thread_id,
        )

    def archive(self, *, thread_id: ThreadId | None = None) -> ArchiveArtifact:
        """Build a command that archives this artifact at this version."""
        return ArchiveArtifact(artifact_id=self.id, base_version=self.version, thread_id=thread_id)


def create_artifact(
    artifact: Artifact,
    *,
    artifact_id: ArtifactId | None = None,
    thread_id: ThreadId | None = None,
) -> CreateArtifact:
    """Build a command that creates ``artifact``."""
    return CreateArtifact(
        artifact_id=artifact_id or new_artifact_id(),
        kind=artifact.kind,
        data=artifact.to_json(),
        thread_id=thread_id,
    )


def artifact_types() -> Mapping[str, type[Artifact]]:
    """Return a read-only view of every registered artifact type, by name."""
    return MappingProxyType(_registry)


def get_artifact_type(kind: str) -> type[Artifact]:
    """Return the artifact type registered under ``kind``.

    Raises:
        NotFound: If no type is registered under that name.
    """
    try:
        return _registry[kind]
    except KeyError:
        raise NotFound("artifact type", kind) from None


def load_artifact(kind: str, data: Mapping[str, Any]) -> Artifact:
    """Validate JSON data as an instance of the artifact type registered under ``kind``.

    Raises:
        NotFound: If no type is registered under that name.
        ValidationFailed: If the data does not validate.
    """
    artifact_type = get_artifact_type(kind)
    try:
        return artifact_type.model_validate(data)
    except ValidationError as error:
        raise ValidationFailed(f"invalid {kind} data", _errors(error)) from error


def load_versioned(
    *,
    id: ArtifactId,
    kind: str,
    version: int,
    data: Mapping[str, Any],
    updated_by: Actor,
    archived: bool = False,
) -> Versioned[Artifact]:
    """Rebuild a stored artifact from its parts, validating the data against its type."""
    return Versioned[Artifact](
        id=id,
        version=version,
        data=load_artifact(kind, data),
        updated_by=updated_by,
        archived=archived,
    )


def _errors(error: ValidationError) -> list[JsonValue]:
    errors: list[JsonValue] = json.loads(error.json(include_url=False))
    return errors


def _snake_case(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name).lower()


def _register(artifact_type: type[Artifact]) -> None:
    existing = _registry.get(artifact_type.kind)
    if existing is not None and _qualified(existing) != _qualified(artifact_type):
        raise TypeError(
            f"artifact type name {artifact_type.kind!r} is already registered by "
            f"{_qualified(existing)}; pass name=... to choose another"
        )
    _registry[artifact_type.kind] = artifact_type


def _qualified(artifact_type: type[Artifact]) -> str:
    return f"{artifact_type.__module__}.{artifact_type.__qualname__}"
