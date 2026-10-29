"""The artifact types: a manifest that names a file's bytes by their digest.

The file is the source of truth, and nothing parses it into fields: an artifact holds where its
bytes are, what was read from them, and how they were made (artifactr ADR-0072).
"""

from typing import Annotated, ClassVar, Final, Literal, Self, override

from pydantic import BaseModel, ConfigDict, Field, model_validator

from artifactr.core import Artifact, WritePolicy

DOCX: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
"""The media type of a Word document, `.docx`."""

XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
"""The media type of an Excel workbook, `.xlsx`."""

PPTX: Final = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
"""The media type of a PowerPoint presentation, `.pptx`."""

PDF: Final = "application/pdf"
"""The media type of a PDF document, `.pdf`."""

DXF: Final = "image/vnd.dxf"
"""The media type of a drawing in AutoCAD's exchange format, `.dxf`."""

DWG: Final = "image/vnd.dwg"
"""The media type of an AutoCAD drawing, `.dwg`."""

PSD: Final = "image/vnd.adobe.photoshop"
"""The media type of a Photoshop document, `.psd`."""

SVG: Final = "image/svg+xml"
"""The media type of an SVG image, `.svg`."""

IDML: Final = "application/vnd.adobe.indesign-idml-package"
"""The media type of an InDesign markup package, `.idml`."""

FIGCRAFT: Final = "application/x-figcraft"
"""The media type of a FigCraft design, `.figcraft`, which has no registered one: a zip holding
its document as JSON."""

FCSTD: Final = "application/x-extension-fcstd"
"""The media type of a FreeCAD document, `.FCStd`, as FreeCAD's own MIME file names it, since it
has no registered one: a zip holding its document as XML and its shapes."""
FCPROJ: Final = "application/x-fcproj"
"""The media type of a FilmCraft video project, `.fcproj`, which has no registered one: JSON."""

ECPROJ: Final = "application/x-ecproj"
"""The media type of an EffectCraft motion graphics project, `.ecproj`, which has no registered
one: JSON."""

SCRAFT: Final = "application/x-scraft"
"""The media type of a SoundCraft audio session, `.scraft`, which has no registered one: JSON."""

BLEND: Final = "application/x-blender"
"""The media type of a Blender file, `.blend`, as the shared MIME-info database names it, since it
has no registered one: Blender's memory, written out in blocks."""

OUTLINE_LIMIT: Final = 4_000
"""The most characters an outline holds: what the agent sees of a file by default."""

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
"""A SHA-256 digest, as 64 lowercase hexadecimal digits."""

Source = Literal["upload", "check_in", "commands", "blank"]
"""How a revision's content was made: uploaded, checked in by a person, by an app's commands, or
as a blank file its app made, for an agent who creates one."""


class Blob(BaseModel):
    """Bytes in the blob store, named by their digest within one artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: Sha256
    size: int = Field(ge=0)
    media_type: str = Field(min_length=1)


class Provenance(BaseModel):
    """How a revision's content was made. Who made it is the revision's actor.

    It is a claim: any surface that commits `edit_artifact` can write anything here, so nothing
    is authorized by it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Source
    app: str | None = None
    """The app that made it, such as `wordcraft`."""

    app_version: str | None = None
    build: str | None = None
    """The digest of the image the app ran in, when a worker ran it."""

    base: Sha256 | None = None
    """The content digest it was made from; None for a new file."""

    commands: Blob | None = None
    """The batch of commands that made it, as canonical JSON."""

    agent: str | None = None
    """The agent that asked for it, as a participant, when a blank file is committed as the
    person the agent's run acts for: the revision's actor is the person."""

    run_id: str | None = None
    """That agent's run."""


class NativeFile(Artifact, abstract=True):
    """A file in a native format: its manifest. Subclass it once per format.

    Agents' edits are proposals by default (`write_policy`): always in a thread in Ask, and in
    Auto unless the application's `agent-writes:direct` setting names the kind (ADR-0009).
    Write policies bind agents only: a person's check-in commits directly.
    """

    formats: ClassVar[frozenset[str]]
    """The media types its content may have."""

    noun: ClassVar[str] = ""
    """What one is called, as the agent is told of it, such as `a Word document`: empty for its
    kind's words, `a word document`."""

    write_policy: ClassVar[WritePolicy] = "propose"

    name: str = Field(min_length=1)
    """The file's name, such as `contract.docx`."""

    content: Blob
    fingerprint: Sha256
    """The digest of the content, normalized: what each save stamps, such as the time, left
    out, so that a save that changes nothing else makes no revision."""

    text: Blob | None = None
    """The file's words as plain text, for diffs and the agent."""

    review: Blob | None = None
    """Its comments and tracked changes, as JSON."""

    outline: str = Field(default="", max_length=OUTLINE_LIMIT)
    pages: int | None = Field(default=None, ge=0)
    provenance: Provenance

    @model_validator(mode="after")
    def _of_its_format(self) -> Self:
        if self.content.media_type not in self.formats:
            raise ValueError(
                f"a {self.kind} holds {sorted(self.formats)}, not {self.content.media_type}"
            )
        return self

    @override
    def render_for_agent(self) -> str:
        """Return the file's name, its pages if they are known, and its outline.

        It does no IO: the agent sees what the app read from the file when the revision was
        made. Its words, review and pages are read through the package's tools.
        """
        heading = self.name
        if self.pages is not None:
            heading += f" ({self.pages} page{'' if self.pages == 1 else 's'})"
        return f"{heading}\n\n{self.outline}" if self.outline else heading


class WordDocument(NativeFile):
    """A Word document, `.docx`: registered as `word_document`."""

    formats: ClassVar[frozenset[str]] = frozenset({DOCX})
    noun: ClassVar[str] = "a Word document"


class Workbook(NativeFile):
    """A spreadsheet workbook, `.xlsx`: registered as `workbook`."""

    formats: ClassVar[frozenset[str]] = frozenset({XLSX})
    noun: ClassVar[str] = "a spreadsheet workbook"


class Presentation(NativeFile):
    """A presentation, `.pptx`: registered as `presentation`."""

    formats: ClassVar[frozenset[str]] = frozenset({PPTX})
    noun: ClassVar[str] = "a presentation"


class PdfDocument(NativeFile):
    """A PDF document, `.pdf`: registered as `pdf_document`."""

    formats: ClassVar[frozenset[str]] = frozenset({PDF})
    noun: ClassVar[str] = "a PDF document"


class Drawing(NativeFile):
    """A drawing, `.dxf` or `.dwg`: registered as `drawing`."""

    formats: ClassVar[frozenset[str]] = frozenset({DXF, DWG})
    noun: ClassVar[str] = "a drawing"


class LayeredImage(NativeFile):
    """A layered image, `.psd`: registered as `layered_image`."""

    formats: ClassVar[frozenset[str]] = frozenset({PSD})
    noun: ClassVar[str] = "a layered image"


class VectorImage(NativeFile):
    """A vector image, `.svg`: registered as `vector_image`."""

    formats: ClassVar[frozenset[str]] = frozenset({SVG})
    noun: ClassVar[str] = "a vector image"


class PageLayout(NativeFile):
    """A page layout, `.idml`: registered as `page_layout`."""

    formats: ClassVar[frozenset[str]] = frozenset({IDML})
    noun: ClassVar[str] = "a page layout"


class Design(NativeFile):
    """A design, `.figcraft`: registered as `design`."""

    formats: ClassVar[frozenset[str]] = frozenset({FIGCRAFT})
    noun: ClassVar[str] = "a design"


class CadModel(NativeFile):
    """A 3D model, `.FCStd`: registered as `cad_model`."""

    formats: ClassVar[frozenset[str]] = frozenset({FCSTD})
    noun: ClassVar[str] = "a 3D model"


class Scene(NativeFile):
    """A 3D scene, `.blend`: registered as `scene`."""

    formats: ClassVar[frozenset[str]] = frozenset({BLEND})
    noun: ClassVar[str] = "a 3D scene"


class VideoProject(NativeFile):
    """A video project, `.fcproj`: registered as `video_project`."""

    formats: ClassVar[frozenset[str]] = frozenset({FCPROJ})
    noun: ClassVar[str] = "a video project"


class MotionGraphics(NativeFile):
    """A motion graphics project, `.ecproj`: registered as `motion_graphics`."""

    formats: ClassVar[frozenset[str]] = frozenset({ECPROJ})
    noun: ClassVar[str] = "a motion graphics project"


class AudioSession(NativeFile):
    """An audio session, `.scraft`: registered as `audio_session`."""

    formats: ClassVar[frozenset[str]] = frozenset({SCRAFT})
    noun: ClassVar[str] = "an audio session"
