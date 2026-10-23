"""The agent's toolset for diagrams: reading them, drawing in them, and editing their elements.

Register :func:`diagram_tools` on the agent as an application toolset (ADR-0017), beside the
``ArtifactWorkspace`` capability with :data:`~artifactr.excalidraw.EXCALIDRAW_TYPES` among its
types (lattice RFC-0006, O6; artifactr ADR-0090)::

    agent = Agent(
        model,
        deps_type=Session[None],
        toolsets=[diagram_tools(converter, blobs=blobs)],
        capabilities=[ArtifactWorkspace(types=[*app_types, *EXCALIDRAW_TYPES])],
    )

The agent draws from Mermaid or from skeletons, which the converter turns into Excalidraw's
elements, and edits by operations on elements by their ids: never raw JSON Patch (ADR-0003).
Its changes are proposals, as a diagram's write policy says, unless the application registers a
type that applies them. The tools are offered only while diagrams are on in the run's workspace.
"""

import json
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic_ai import BinaryContent, FunctionToolset, ModelRetry, RunContext, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset

from artifactr.agent import Session, describe_outcome
from artifactr.core import CreateArtifact, EditArtifact, new_artifact_id
from artifactr.excalidraw.converter import (
    MAX_MERMAID,
    MAX_SKELETONS,
    ConversionFailed,
    Converted,
    Converter,
)
from artifactr.excalidraw.integrations import EXCALIDRAW
from artifactr.excalidraw.patches import element_patch
from artifactr.excalidraw.types import (
    MAX_NAME,
    MAX_NONCE,
    Diagram,
    DiagramFile,
    Element,
    ElementId,
)
from artifactr.files.blobs import Blobs
from artifactr.workspace import Scope, Workspace
from lattice_core.integrations import Defaults, Integrations

__all__ = [
    "PAGE",
    "Connect",
    "Delete",
    "Move",
    "Op",
    "Relabel",
    "Resize",
    "Restyle",
    "diagram_tools",
]

PAGE: Final = 100
"""The most elements `read_diagram` gives at once."""

GAP: Final = 120
"""How far to the right of what a diagram holds a new drawing in it starts."""


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ElementId


class Move(_Op):
    """Move an element to a place."""

    op: Literal["move"] = "move"
    x: float
    y: float


class Resize(_Op):
    """Give an element a size."""

    op: Literal["resize"] = "resize"
    width: Annotated[float, Field(gt=0, le=100_000)]
    height: Annotated[float, Field(gt=0, le=100_000)]


class Restyle(_Op):
    """Change an element's colours: a CSS colour, such as `#1e1e1e` or `transparent`."""

    op: Literal["restyle"] = "restyle"
    stroke_color: Annotated[str, Field(max_length=32)] | None = None
    background_color: Annotated[str, Field(max_length=32)] | None = None


class Relabel(_Op):
    """Change the words of a text, or of the label bound in a shape or an arrow."""

    op: Literal["relabel"] = "relabel"
    text: Annotated[str, Field(max_length=2_000)]


class Delete(_Op):
    """Delete an element, and the label bound in it."""

    op: Literal["delete"] = "delete"


class Connect(BaseModel):
    """Draw an arrow from one element to another, with a label if given."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["connect"] = "connect"
    start: ElementId
    end: ElementId
    label: Annotated[str, Field(max_length=2_000)] | None = None


Op = Annotated[Move | Resize | Restyle | Relabel | Delete | Connect, Field(discriminator="op")]
"""One edit of a diagram's elements, by their ids."""


def diagram_tools(
    converter: Converter,
    *,
    blobs: Blobs | None = None,
    view: bool = False,
    integrations: Integrations | None = None,
) -> AbstractToolset[Session[Any]]:
    """Build the toolset: `read_diagram`, `draw_mermaid`, `draw`, `edit_elements`, `view_diagram`.

    Args:
        converter: What turns Mermaid and skeletons into elements, and renders a diagram: the
            worker's, or a fake one.
        blobs: Where the images a conversion makes are kept, the native files' store. Without
            one, a drawing that holds an image is refused, and the agent is told to draw shapes.
        view: Offer `view_diagram`, which gives the model a PNG of a diagram: off unless the
            model can see images.
        integrations: Whether diagrams are on in the run's workspace, asked before each model
            request: off, the tools are left out of the request. Lattice-core's ``Defaults``,
            where diagrams are off, if omitted.
    """
    # A refusal says what to fix; a model may need a few tries at a drawing, as at a form.
    toolset = FunctionToolset[Session[Any]](max_retries=3)

    @toolset.tool
    async def read_diagram(
        ctx: RunContext[Session[Any]], id: str, page: Annotated[int, Field(ge=0)] = 0
    ) -> str:
        """Read a diagram: its description, its version, and a page of its live elements as JSON.

        Each element is its id, type, label, place, size and what it binds. Edit by these ids.

        Args:
            id: The diagram.
            page: Which page of elements, from 0, at most 100 elements each.
        """
        current = await ctx.deps.workspace.get(Diagram, id)
        live = [e for e in current.data.elements.values() if not e.is_deleted]
        labels = _labels(live)
        shown = live[page * PAGE : (page + 1) * PAGE]
        more = len(live) > (page + 1) * PAGE
        listed = [_compact(element, labels) for element in shown]
        return "\n".join(
            [
                current.data.render_for_agent(),
                f"Version {current.version}. Elements {page * PAGE + 1} to "
                f"{page * PAGE + len(shown)} of {len(live)}"
                + (f"; read page {page + 1} for more." if more else "."),
                json.dumps(listed, separators=(",", ":")),
            ]
        )

    @toolset.tool
    async def draw_mermaid(
        ctx: RunContext[Session[Any]],
        mermaid: Annotated[str, Field(max_length=MAX_MERMAID)],
        summary: Annotated[str, Field(max_length=200)],
        name: Annotated[str, Field(max_length=MAX_NAME)] | None = None,
        id: str | None = None,
    ) -> str:
        """Draw a Mermaid diagram as a new diagram, or beside what an existing one holds.

        Flowcharts, sequences, classes, ER and state diagrams become shapes and arrows that can
        be edited; other kinds become one picture. Prefer this to `draw`.

        Args:
            mermaid: The Mermaid source.
            summary: What the drawing shows, in a few words, said with the change.
            name: The new diagram's name; required unless `id` is given.
            id: The diagram to draw into, if not a new one.
        """
        return await _drawn(ctx.deps, lambda: converter.mermaid(mermaid), summary, name, id)

    @toolset.tool
    async def draw(
        ctx: RunContext[Session[Any]],
        skeletons: Annotated[list[dict[str, JsonValue]], Field(max_length=MAX_SKELETONS)],
        summary: Annotated[str, Field(max_length=200)],
        name: Annotated[str, Field(max_length=MAX_NAME)] | None = None,
        id: str | None = None,
    ) -> str:
        """Draw elements from skeletons, as a new diagram or beside what an existing one holds.

        A skeleton is `{"type": ..., "x": ..., "y": ...}`, with `width`, `height`, a `label`,
        an `id` of your own to bind to, and, for an `arrow`, `start` and `end` as `{"id": ...}`.
        Types: rectangle, ellipse, diamond, arrow, line, text, frame.

        Args:
            skeletons: The elements, as skeletons.
            summary: What the drawing shows, in a few words, said with the change.
            name: The new diagram's name; required unless `id` is given.
            id: The diagram to draw into, if not a new one.
        """
        return await _drawn(ctx.deps, lambda: converter.skeletons(skeletons), summary, name, id)

    @toolset.tool
    async def edit_elements(
        ctx: RunContext[Session[Any]],
        id: str,
        base_version: int,
        ops: Annotated[list[Op], Field(min_length=1, max_length=MAX_SKELETONS)],
        summary: Annotated[str, Field(max_length=200)],
    ) -> str:
        """Edit a diagram's elements by their ids, against the version you read.

        Args:
            id: The diagram.
            base_version: The version `read_diagram` gave; read again if it has moved on.
            ops: The edits, in order: move, resize, restyle, relabel, delete, connect.
            summary: What the edit does, in a few words, said with the change.
        """
        workspace = ctx.deps.workspace
        current = await workspace.get(Diagram, id)
        if current.version != base_version:
            raise ModelRetry(
                f"Diagram {id} is at version {current.version}, not {base_version}: read it again"
            )
        elements = dict(current.data.elements)
        for op in ops:
            _apply(elements, op)
        patch = element_patch(current.data, elements)
        command = EditArtifact(
            artifact_id=id,
            base_version=base_version,
            patch=patch,
            summary=summary,
            thread_id=ctx.deps.thread_id,
        )
        return describe_outcome(await workspace.commit(command))

    if view:

        @toolset.tool
        async def view_diagram(ctx: RunContext[Session[Any]], id: str) -> BinaryContent:
            """Look at a diagram, rendered as a PNG.

            Args:
                id: The diagram.
            """
            workspace = ctx.deps.workspace
            current = await workspace.get(Diagram, id)
            files = await _images(blobs, workspace, id, current.data.files)
            try:
                png = await converter.render(current.data, files, as_="png")
            except ConversionFailed as failed:
                raise ModelRetry(f"The diagram can't be shown: {failed}") from failed
            return BinaryContent(data=png, media_type="image/png")

    async def _drawn(
        deps: Session[Any],
        convert: Callable[[], Awaitable[Converted]],
        summary: str,
        name: str | None,
        id: str | None,
    ) -> str:
        try:
            converted = await convert()
        except ConversionFailed as failed:
            raise ModelRetry(f"Not drawn ({failed.reason}): {failed}") from failed
        workspace = deps.workspace
        if id is None:
            if name is None:
                raise ModelRetry("A new diagram needs a `name`, or give the `id` to draw into")
            artifact_id = new_artifact_id()
            files = await _stored(blobs, workspace, artifact_id, converted)
            elements = _with_files(converted.elements, files)
            diagram = _diagram(name, elements, _by_digest(files))
            command = CreateArtifact(
                kind=Diagram.kind,
                artifact_id=artifact_id,
                data=diagram.to_json(),
                thread_id=deps.thread_id,
            )
            return describe_outcome(await workspace.commit(command))
        current = await workspace.get(Diagram, id)
        files = await _stored(blobs, workspace, id, converted)
        placed = _beside(current.data.elements.values(), _with_files(converted.elements, files))
        clashing = sorted(set(placed) & set(current.data.elements))
        if clashing:
            raise ModelRetry(f"Diagram {id} already has elements {clashing[:5]}: use other ids")
        merged = {**current.data.elements, **placed}
        patch = element_patch(current.data, merged, _by_digest(files))
        command = EditArtifact(
            artifact_id=id,
            base_version=current.version,
            patch=patch,
            summary=summary,
            thread_id=deps.thread_id,
        )
        return describe_outcome(await workspace.commit(command))

    async def offered(
        ctx: RunContext[Session[Any]], tools: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        workspace = ctx.deps.workspace
        asked = integrations or Defaults()
        on = await asked.is_enabled(workspace.tenant_id, workspace.workspace_id, EXCALIDRAW)
        return tools if on else []

    return toolset.prepared(offered)


def _diagram(
    name: str, elements: Mapping[str, Element], files: Mapping[str, DiagramFile]
) -> Diagram:
    try:
        return Diagram(name=name, elements=dict(elements), files=dict(files))
    except ValueError as error:
        raise ModelRetry(f"Not drawn: {error}") from error


async def _stored(
    blobs: Blobs | None, workspace: Workspace, artifact_id: str, converted: Converted
) -> dict[str, DiagramFile]:
    """Keep a conversion's images in the store: each by the `fileId` the conversion gave it."""
    if not converted.files:
        return {}
    if blobs is None:
        raise ModelRetry("Images aren't kept here: draw it as shapes, such as a flowchart")
    try:
        parts = [(file.content(), file.media_type) for file in converted.files.values()]
    except ConversionFailed as failed:
        raise ModelRetry(f"Not drawn: {failed}") from failed
    stored = await blobs.put_all(
        Scope(workspace.tenant_id, workspace.workspace_id), artifact_id, parts
    )
    return {
        given: DiagramFile(sha256=blob.sha256, size=blob.size, media_type=blob.media_type)
        for given, blob in zip(converted.files, stored, strict=True)
    }


def _with_files(
    elements: Sequence[Element], files: Mapping[str, DiagramFile]
) -> dict[str, Element]:
    """The elements by id, each image's `fileId` the digest its bytes are kept under."""
    found: dict[str, Element] = {}
    for element in elements:
        given = (element.model_extra or {}).get("fileId")
        if isinstance(given, str) and given in files:
            element = _changed(element, {"fileId": files[given].sha256}, bump=False)
        found[element.id] = element
    return found


def _by_digest(files: Mapping[str, DiagramFile]) -> dict[str, DiagramFile]:
    """The images as a diagram keeps them: by their digest."""
    return {file.sha256: file for file in files.values()}


async def _images(
    blobs: Blobs | None, workspace: Workspace, artifact_id: str, files: Mapping[str, DiagramFile]
) -> dict[str, bytes]:
    """The bytes of a diagram's images, those the store still has."""
    if blobs is None:
        return {}
    scope = Scope(workspace.tenant_id, workspace.workspace_id)
    found: dict[str, bytes] = {}
    for digest in files:
        data = await blobs.get(scope, artifact_id, digest)
        if data is not None:
            found[digest] = data
    return found


def _changed(element: Element, fields: Mapping[str, JsonValue], *, bump: bool = True) -> Element:
    """An element with fields changed: as a new version, with a new nonce, unless `bump` is off."""
    data = {**element.model_dump(mode="json"), **fields}
    if bump:
        data |= {"version": element.version + 1, "versionNonce": secrets.randbelow(MAX_NONCE) + 1}
    return Element.model_validate(data)


def _labels(elements: Sequence[Element]) -> dict[str, Element]:
    """Each element's bound label: the text whose container it is."""
    found: dict[str, Element] = {}
    for element in elements:
        container = (element.model_extra or {}).get("containerId")
        if element.type == "text" and isinstance(container, str):
            found[container] = element
    return found


def _compact(element: Element, labels: Mapping[str, Element]) -> dict[str, JsonValue]:
    """What the agent reads of an element: its id, type, label, place, size and bindings."""
    extra = element.model_extra or {}
    label = labels.get(element.id)
    shown: dict[str, JsonValue] = {"id": element.id, "type": element.type}
    if label is not None:
        shown["label"] = (label.model_extra or {}).get("text")
    elif element.type == "text":
        shown["text"] = extra.get("text")
    for key in ("x", "y", "width", "height"):
        if isinstance(value := extra.get(key), int | float):
            shown[key] = round(value)
    for key in ("startBinding", "endBinding"):
        match extra.get(key):
            case {"elementId": str(bound)}:
                shown[key.removesuffix("Binding")] = bound
            case _:
                pass
    return shown


def _beside(existing: Iterable[Element], drawn: Mapping[str, Element]) -> dict[str, Element]:
    """New elements moved to the right of what a diagram holds, so nothing is drawn over."""
    edges = [
        x + width
        for e in existing
        if not e.is_deleted
        and isinstance(x := (e.model_extra or {}).get("x"), int | float)
        and isinstance(width := (e.model_extra or {}).get("width", 0), int | float)
    ]
    if not edges:
        return dict(drawn)
    shift = max(edges) + GAP
    return {
        key: _changed(e, {"x": x + shift}, bump=False)
        if isinstance(x := (e.model_extra or {}).get("x"), int | float)
        else e
        for key, e in drawn.items()
    }


def _apply(
    elements: dict[str, Element], op: Move | Resize | Restyle | Relabel | Delete | Connect
) -> None:
    """Carry an edit out on a diagram's elements, or tell the model why it can't be."""
    if isinstance(op, Connect):
        for end in (op.start, op.end):
            _live(elements, end)
        arrow_id = f"arrow-{secrets.token_hex(6)}"
        ends: dict[str, JsonValue] = {
            "startBinding": {"elementId": op.start},
            "endBinding": {"elementId": op.end},
        }
        elements[arrow_id] = _changed(_new(arrow_id, "arrow"), ends, bump=False)
        if op.label:
            label_id = f"label-{secrets.token_hex(6)}"
            label = {"text": op.label, "containerId": arrow_id}
            elements[label_id] = _changed(_new(label_id, "text"), label, bump=False)
        return
    element = _live(elements, op.id)
    match op:
        case Move():
            elements[op.id] = _changed(element, {"x": op.x, "y": op.y})
        case Resize():
            elements[op.id] = _changed(element, {"width": op.width, "height": op.height})
        case Restyle():
            colours = {"strokeColor": op.stroke_color, "backgroundColor": op.background_color}
            given = {key: value for key, value in colours.items() if value is not None}
            elements[op.id] = _changed(element, given)
        case Relabel():
            target = (
                element if element.type == "text" else _labels(list(elements.values())).get(op.id)
            )
            if target is None or target.is_deleted:
                label_id = f"label-{secrets.token_hex(6)}"
                label = {"text": op.text, "containerId": op.id}
                elements[label_id] = _changed(_new(label_id, "text"), label, bump=False)
            else:
                elements[target.id] = _changed(target, {"text": op.text})
        case _:  # a delete, the one edit left
            elements[op.id] = _changed(element, {"isDeleted": True})
            label = _labels(list(elements.values())).get(op.id)
            if label is not None and not label.is_deleted:
                elements[label.id] = _changed(label, {"isDeleted": True})


def _live(elements: Mapping[str, Element], key: str) -> Element:
    element = elements.get(key)
    if element is None or element.is_deleted:
        raise ModelRetry(f"There is no element {key}: read the diagram for its ids")
    return element


def _new(key: str, kind: str) -> Element:
    return Element.model_validate(
        {
            "id": key,
            "type": kind,
            "version": 1,
            "versionNonce": secrets.randbelow(MAX_NONCE) + 1,
            "x": 0,
            "y": 0,
        }
    )
