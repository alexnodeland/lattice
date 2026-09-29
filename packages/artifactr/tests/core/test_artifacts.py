"""Artifact types: registration, rendering, and building commands from versioned data."""

from typing import ClassVar

import pytest

from artifactr.core import (
    ArchiveArtifact,
    Artifact,
    EditArtifact,
    MarkdownArtifact,
    NotFound,
    TextEdits,
    UserActor,
    ValidationFailed,
    Versioned,
    WritePolicy,
    apply_patch,
    artifact_types,
    create_artifact,
    get_artifact_type,
    load_artifact,
)
from tests.artifact_types import Checklist, Item, Note

ALICE = UserActor(id="alice")


def test_types_register_under_a_snake_case_name() -> None:
    class ReleaseNotes(MarkdownArtifact):
        pass

    class HTTPRoute(Artifact):
        path: str = "/"

    assert ReleaseNotes.kind == "release_notes"
    assert HTTPRoute.kind == "http_route"
    assert get_artifact_type("release_notes") is ReleaseNotes
    assert artifact_types()["http_route"] is HTTPRoute


def test_a_name_can_be_given_and_abstract_bases_are_not_registered() -> None:
    class Base(Artifact, abstract=True):
        owner: str = ""

    class Spec(Base, name="product_spec"):
        write_policy: ClassVar[WritePolicy] = "propose"

    assert Spec.kind == "product_spec"
    assert Spec.write_policy == "propose"
    assert "base" not in artifact_types()
    assert list(Spec.model_fields) == ["owner"]


def test_a_name_cannot_be_registered_twice() -> None:
    with pytest.raises(TypeError, match="already registered"):

        class Imposter(Artifact, name="note"):
            pass


def test_redefining_the_same_class_replaces_it() -> None:
    def define() -> type[Artifact]:
        class Scratch(Artifact, name="scratch"):
            pass

        return Scratch

    first, second = define(), define()
    assert first is not second
    assert get_artifact_type("scratch") is second


def test_unknown_types_and_invalid_data_are_rejected() -> None:
    with pytest.raises(NotFound):
        get_artifact_type("nonexistent")
    with pytest.raises(ValidationFailed) as failed:
        load_artifact("note", {"title": 5})
    error = failed.value.errors[0]
    assert isinstance(error, dict)
    assert error["loc"] == ["title"]


def test_rendering_for_the_agent() -> None:
    assert Note(text="# Plan").render_for_agent() == "# Plan"
    checklist = Checklist(title="Launch")
    assert checklist.render_for_agent() == checklist.model_dump_json(indent=2)
    assert Note().describe_change(Note()) is None


def test_edit_diffs_a_mutated_copy() -> None:
    items = {"t1": Item(title="Write docs")}
    stored = Versioned[Checklist](id="c1", version=4, data=Checklist(items=items), updated_by=ALICE)

    def check(checklist: Checklist) -> str:
        checklist.items["t1"].done = True
        return "ignored"

    command = stored.edit(check, summary="checked docs", thread_id="t1")
    assert isinstance(command, EditArtifact)
    assert (command.artifact_id, command.base_version, command.summary) == ("c1", 4, "checked docs")
    assert command.thread_id == "t1"
    assert stored.data.items["t1"].done is False, "the stored data is untouched"
    assert apply_patch(stored.data.to_json(), command.patch)["items"] == {
        "t1": {"title": "Write docs", "done": True}
    }
    assert stored.kind == "checklist"


def test_edit_text_and_archive_build_commands() -> None:
    stored = Versioned[Note](id="n1", version=2, data=Note(text="Friday"), updated_by=ALICE)
    edit = stored.edit_text("Friday", "Monday", summary="moved")
    assert isinstance(edit.patch, TextEdits)
    assert (edit.patch.field, edit.patch.edits[0].new, edit.summary) == ("text", "Monday", "moved")
    archive = stored.archive(thread_id="t1")
    assert archive == ArchiveArtifact(
        artifact_id="n1", base_version=2, thread_id="t1", proposal_id=archive.proposal_id
    )


def test_create_artifact_builds_a_command() -> None:
    command = create_artifact(Note(title="Ideas"), artifact_id="n9", thread_id="t1")
    assert (command.artifact_id, command.kind, command.thread_id) == ("n9", "note", "t1")
    assert command.data == {"text": "", "title": "Ideas"}
    assert create_artifact(Note()).artifact_id.startswith("art_")


def test_versioned_serializes_the_concrete_type_and_its_kind() -> None:
    stored = Versioned[Artifact](id="n1", version=1, data=Note(title="x"), updated_by=ALICE)
    dumped = stored.model_dump(mode="json")
    assert (dumped["kind"], dumped["data"]) == ("note", {"text": "", "title": "x"})
    assert Versioned[Note].model_validate(dumped) == stored
