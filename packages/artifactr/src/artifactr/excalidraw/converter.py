"""What draws and renders diagrams for the agent: the converter, a port, and its worker's client.

The agent writes Mermaid or skeletons; the converter turns them into Excalidraw's elements, as
Excalidraw's own `parseMermaidToExcalidraw` and `convertToExcalidrawElements` do, and renders a
diagram as SVG or PNG. Lattice's runs it in a worker of its own, headless Chromium on a network
with no way out (lattice RFC-0006, O7; artifactr ADR-0088), which
[`WorkerConverter`][artifactr.excalidraw.converter.WorkerConverter] calls over HTTP;
[`FakeConverter`][artifactr.excalidraw.converter.FakeConverter] draws without one, for tests and
an application that has none (artifactr ADR-0090).
"""

import base64
import binascii
import hashlib
import json
import re
import struct
import zlib
from collections.abc import Mapping, Sequence
from typing import Annotated, Final, Literal, Protocol, Self
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import anyio
import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from artifactr.excalidraw.types import MAX_ELEMENTS, Diagram, Element

__all__ = [
    "DEADLINE",
    "MAX_MERMAID",
    "MAX_SKELETONS",
    "Colour",
    "ConversionFailed",
    "Converted",
    "ConvertedFile",
    "Converter",
    "FakeConverter",
    "Format",
    "Reason",
    "Skeleton",
    "WorkerConverter",
]

DEADLINE: Final = 10.0
"""The seconds a conversion or a render may take, as the worker is held to them (ADR-0088)."""

GRACE: Final = 5.0
"""The seconds a reply may take past its deadline, for the worker to say how it failed."""

MAX_MERMAID: Final = 50_000
"""The longest Mermaid source the agent may send, in characters."""

MAX_SKELETONS: Final = 500
"""The most skeletons the agent may send at once."""

MAX_IMAGE_BYTES: Final = 2 * 1024 * 1024
"""The largest image a conversion may give, before base64: a Mermaid diagram Excalidraw draws
only as a picture, such as a Gantt chart."""

MAX_IMAGES: Final = 8
"""The most images a conversion may give."""

MAX_REPLY: Final = 2 * 1024 * 1024 + MAX_IMAGES * MAX_IMAGE_BYTES * 4 // 3
"""The most bytes a conversion's reply may hold: its elements, and its images as base64."""

MAX_RENDERED: Final = 8 * 1024 * 1024
"""The most bytes a rendered diagram may be."""

MAX_RENDERING: Final = 16 * 1024 * 1024
"""The most bytes a render may send the worker: the diagram, and its images as base64."""

PLACE: Final = 10_000_000.0
"""How far from the origin anything the agent places may be, either way."""

PNG: Final = b"\x89PNG\r\n\x1a\n"
"""A PNG's first bytes."""

Colour = Annotated[str, Field(pattern=r"^(#[0-9a-fA-F]{3,8}|transparent|[a-z]{3,20})$")]
"""A colour an element may be given: hex, `transparent`, or a CSS colour's name."""

Coordinate = Annotated[float, Field(allow_inf_nan=False, ge=-PLACE, le=PLACE)]
"""A place on the canvas, finite and within reach."""

Extent = Annotated[float, Field(allow_inf_nan=False, gt=0, le=PLACE)]
"""A size, finite and more than nothing."""

Words = Annotated[str, Field(max_length=2_000)]
"""Words written in a diagram."""

Format = Literal["svg", "png"]
"""What a diagram renders as."""

Reason = Literal["invalid", "unsupported", "too_large", "timeout", "crashed"]
"""Why a conversion failed: what the agent sent was wrong; it is a kind the converter doesn't
draw; it, or what it made, was past a limit; it took past its deadline; or the worker failed."""


class ConversionFailed(Exception):
    """A conversion or a render that didn't give a diagram, and why, in words the agent reads."""

    def __init__(self, reason: Reason, message: str) -> None:
        super().__init__(message)
        self.reason: Reason = reason


class Bound(BaseModel):
    """An element an arrow is bound to, by its id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class Skeleton(BaseModel):
    """An element to draw, given by what the agent may set of it, and nothing else.

    The worker's contract is these fields alone: its type, an id of the agent's own to bind to,
    its place and size, its label (or a text's words), its colours, and, for an arrow or a line,
    what it starts and ends at.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["rectangle", "ellipse", "diamond", "arrow", "line", "text", "frame"]
    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")] | None = None
    x: Coordinate = 0
    y: Coordinate = 0
    width: Extent | None = None
    height: Extent | None = None
    label: Words | None = None
    text: Words | None = None
    stroke_color: Colour | None = None
    background_color: Colour | None = None
    start: Bound | None = None
    end: Bound | None = None


class ConvertedFile(BaseModel):
    """An image a conversion made: its bytes, as base64, and its media type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    media_type: Literal["image/svg+xml", "image/png"]
    data: Annotated[str, Field(max_length=MAX_IMAGE_BYTES * 4 // 3 + 4)]

    def content(self) -> bytes:
        """The image's bytes.

        Raises:
            ConversionFailed: If its data isn't base64.
        """
        try:
            return base64.b64decode(self.data, validate=True)
        except binascii.Error as error:
            raise ConversionFailed(
                "crashed", "the converter gave an image that isn't base64"
            ) from error


class Converted(BaseModel):
    """What a conversion made: elements, and the images they show, by their `fileId`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    elements: list[Element] = Field(max_length=MAX_ELEMENTS)
    files: dict[str, ConvertedFile] = Field(default_factory=dict[str, ConvertedFile])

    @field_validator("files")
    @classmethod
    def _few(cls, files: dict[str, ConvertedFile]) -> dict[str, ConvertedFile]:
        if len(files) > MAX_IMAGES:
            msg = f"a conversion gives at most {MAX_IMAGES} images"
            raise ValueError(msg)
        return files

    @model_validator(mode="after")
    def _once(self) -> Self:
        ids = [element.id for element in self.elements]
        if len(ids) != len(set(ids)):
            msg = "a conversion gives each element once"
            raise ValueError(msg)
        return self


class Converter(Protocol):
    """What draws and renders diagrams: Mermaid or skeletons into elements, a diagram into an image.

    Each call fails with [`ConversionFailed`][artifactr.excalidraw.converter.ConversionFailed]
    and never with anything else, within its deadline and a little more.
    """

    async def mermaid(self, source: str, *, deadline: float = DEADLINE) -> Converted:
        """Draw a Mermaid diagram: flowcharts, sequences, classes, ER and states as shapes."""
        ...

    async def skeletons(
        self, skeletons: Sequence[Skeleton], *, deadline: float = DEADLINE
    ) -> Converted:
        """Draw skeletons: elements given by their type, place, size, label and what they bind."""
        ...

    async def render(
        self,
        diagram: Diagram,
        files: Mapping[str, bytes],
        *,
        as_: Format,
        deadline: float = DEADLINE,
    ) -> bytes:
        """Render a diagram, with the images it shows, as SVG or PNG: a PNG, or a checked SVG."""
        ...


class WorkerConverter:
    """The converter in lattice's worker, over HTTP on the deployment's internal network.

    A call is a `POST` of JSON with the worker's token. The worker replies with what it made, or
    with `{"reason": ..., "message": ...}` and a 4xx or a 5xx; anything else, and a worker that
    can't be reached or doesn't reply within the deadline and its grace, is a failure too.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @classmethod
    def at(cls, url: str, *, token: str, transport: httpx.AsyncBaseTransport | None = None) -> Self:
        """The worker at `url`.

        Args:
            url: The worker's base URL, on the deployment's internal network.
            token: The token the deployment generated for it.
            transport: How requests are sent, for tests; HTTP by default.
        """
        client = httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
            # A connection for each call, as native files' worker has (artifactr.files.worker).
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        return cls(client)

    async def aclose(self) -> None:
        """Close the connections to the worker."""
        await self._client.aclose()

    async def mermaid(self, source: str, *, deadline: float = DEADLINE) -> Converted:
        """Draw a Mermaid diagram in the worker."""
        _within("Mermaid's source", len(source), MAX_MERMAID, "characters")
        sent = {"source": source, "deadline": deadline}
        return _converted(await self._post("/mermaid", sent, deadline, MAX_REPLY))

    async def skeletons(
        self, skeletons: Sequence[Skeleton], *, deadline: float = DEADLINE
    ) -> Converted:
        """Draw skeletons in the worker."""
        _within("the skeletons", len(skeletons), MAX_SKELETONS, "skeletons")
        sent = {
            "skeletons": [each.model_dump(exclude_none=True) for each in skeletons],
            "deadline": deadline,
        }
        return _converted(await self._post("/skeletons", sent, deadline, MAX_REPLY))

    async def render(
        self,
        diagram: Diagram,
        files: Mapping[str, bytes],
        *,
        as_: Format,
        deadline: float = DEADLINE,
    ) -> bytes:
        """Render a diagram in the worker."""
        _within("the images", sum(len(data) for data in files.values()), MAX_RENDERING, "bytes")
        sent = {
            "diagram": diagram.to_json(),
            "files": {key: base64.b64encode(data).decode() for key, data in files.items()},
            "as": as_,
            "deadline": deadline,
        }
        return checked(await self._post("/render", sent, deadline, MAX_RENDERED), as_)

    async def _post(
        self, path: str, body: Mapping[str, object], deadline: float, most: int
    ) -> bytes:
        """Send a call, and read its reply, all within the deadline and its grace, up to `most`."""
        try:
            content = json.dumps(body, allow_nan=False, separators=(",", ":")).encode()
        except ValueError as error:
            raise ConversionFailed("invalid", "it holds a number JSON can't") from error
        _within("the call", len(content), MAX_RENDERING, "bytes")
        headers = {"Content-Type": "application/json"}
        try:
            with anyio.fail_after(deadline + GRACE):
                async with self._client.stream(
                    "POST", path, content=content, headers=headers
                ) as reply:
                    read = await _read(reply, most)
        except TimeoutError as error:
            raise ConversionFailed(
                "timeout", f"the converter took more than {deadline:g}s"
            ) from error
        except httpx.TimeoutException as error:
            raise ConversionFailed(
                "timeout", f"the converter took more than {deadline:g}s"
            ) from error
        except httpx.HTTPError as error:
            raise ConversionFailed("crashed", "the converter couldn't be reached") from error
        if reply.is_success:
            return read
        raise _refused(reply.status_code, read)


class FakeConverter:
    """A converter with no worker, which draws what it can by itself.

    It draws a flowchart's `A --> B` and `A -- label --> B` lines as boxes and arrows, and
    skeletons as their elements; it refuses any other Mermaid as a kind it doesn't draw, and
    renders a diagram as a small SVG of its description. Its elements are what Excalidraw's
    would be in shape, not in look: enough for tests and for an application without the worker.
    """

    def __init__(self) -> None:
        self._made = 0

    async def mermaid(self, source: str, *, deadline: float = DEADLINE) -> Converted:
        """Draw a flowchart's edges; refuse anything else."""
        _in_time(deadline)
        _within("Mermaid's source", len(source), MAX_MERMAID, "characters")
        lines = [line.strip() for line in source.strip().splitlines() if line.strip()]
        if not lines or not lines[0].startswith(("flowchart", "graph")):
            raise ConversionFailed("unsupported", "this converter draws flowcharts alone")
        nodes: dict[str, Element] = {}
        made: list[Element] = []
        for line in lines[1:]:
            parts = line.replace("-- ", "--").split("-->")
            if len(parts) != 2:
                raise ConversionFailed("invalid", f"not an edge: {line!r}")
            start, label = [*parts[0].split("--", 1), ""][:2]
            ends = [self._node(nodes, made, name.strip()) for name in (start, parts[1])]
            ends_bound: dict[str, JsonValue] = {
                "startBinding": {"elementId": ends[0].id},
                "endBinding": {"elementId": ends[1].id},
            }
            arrow = self._element("arrow", None, ends_bound)
            made.append(arrow)
            if label.strip():
                made.append(
                    self._element("text", None, {"text": label.strip(), "containerId": arrow.id})
                )
            if len(made) > MAX_ELEMENTS:
                raise ConversionFailed("too_large", f"it makes more than {MAX_ELEMENTS} elements")
        return _made(made)

    async def skeletons(
        self, skeletons: Sequence[Skeleton], *, deadline: float = DEADLINE
    ) -> Converted:
        """Draw each skeleton as its element, its label a text bound in it."""
        _in_time(deadline)
        _within("the skeletons", len(skeletons), MAX_SKELETONS, "skeletons")
        made: list[Element] = []
        for skeleton in skeletons:
            given: dict[str, JsonValue] = {
                "width": skeleton.width,
                "height": skeleton.height,
                "text": skeleton.text,
                "strokeColor": skeleton.stroke_color,
                "backgroundColor": skeleton.background_color,
            }
            fields: dict[str, JsonValue] = {
                "x": skeleton.x,
                "y": skeleton.y,
                **{key: value for key, value in given.items() if value is not None},
            }
            for key, bound in (("startBinding", skeleton.start), ("endBinding", skeleton.end)):
                if bound is not None:
                    fields[key] = {"elementId": bound.id}
            element = self._element(skeleton.type, skeleton.id, fields)
            made.append(element)
            if skeleton.label is not None:
                label = {"text": skeleton.label, "containerId": element.id}
                made.append(self._element("text", None, label))
        return _made(made)

    async def render(
        self,
        diagram: Diagram,
        files: Mapping[str, bytes],
        *,
        as_: Format,
        deadline: float = DEADLINE,
    ) -> bytes:
        """A one-pixel PNG, or a small SVG, holding the diagram's description."""
        _in_time(deadline)
        said = f"{diagram.render_for_agent()} ({len(files)} images)"
        if as_ == "png":
            return _png(said)
        return f'<svg xmlns="http://www.w3.org/2000/svg"><desc>{escape(said)}</desc></svg>'.encode()

    def _node(self, nodes: dict[str, Element], made: list[Element], name: str) -> Element:
        if name not in nodes:
            nodes[name] = self._element("rectangle", None, {"x": len(nodes) * 200, "y": 0})
            made.append(nodes[name])
            made.append(self._element("text", None, {"text": name, "containerId": nodes[name].id}))
        return nodes[name]

    def _element(
        self, kind: str, given: str | None, fields: Mapping[str, JsonValue] | None = None
    ) -> Element:
        self._made += 1
        made = given if given is not None else f"fake{self._made}"
        data: dict[str, JsonValue] = {
            "x": 0,
            "y": 0,
            "width": 160,
            "height": 80,
            **(fields or {}),
            "id": made,
            "type": kind,
            "version": 1,
            "versionNonce": int(hashlib.sha256(made.encode()).hexdigest()[:7], 16),
        }
        # What a skeleton may set is checked as it is made, so this is an element.
        return Element.model_validate(data)


def _in_time(deadline: float) -> None:
    if deadline <= 0:
        raise ConversionFailed("timeout", "no time was given to draw it")


def _within(what: str, size: int, most: int, unit: str) -> None:
    if size > most:
        raise ConversionFailed("too_large", f"{what} is {size} {unit}: at most {most}")


def _made(made: list[Element]) -> Converted:
    try:
        return Converted(elements=made)
    except ValidationError as error:
        raise ConversionFailed("invalid", f"not drawn: {error.errors()[0]['msg']}") from error


async def _read(reply: httpx.Response, most: int) -> bytes:
    read = bytearray()
    async for chunk in reply.aiter_bytes():
        read += chunk
        if len(read) > most:
            raise ConversionFailed("too_large", f"the converter's reply is more than {most} bytes")
    return bytes(read)


def _converted(reply: bytes) -> Converted:
    try:
        return Converted.model_validate_json(reply)
    except ValidationError as error:
        raise ConversionFailed("crashed", "the converter replied with something else") from error


SAID: Final[frozenset[Reason]] = frozenset({"invalid", "unsupported", "too_large"})
"""The failures whose words, the worker's own, may reach the model: they are about what it sent."""


def _refused(status: int, reply: bytes) -> ConversionFailed:
    try:
        said = _Refusal.model_validate_json(reply)
    except ValidationError:
        return ConversionFailed("crashed", f"the converter answered {status}")
    if said.reason not in SAID:
        words = (
            "the converter took too long" if said.reason == "timeout" else "the converter failed"
        )
        return ConversionFailed(said.reason, words)
    return ConversionFailed(said.reason, said.message[:500])


class _Refusal(BaseModel):
    """What the worker says of a call it couldn't carry out."""

    reason: Reason
    message: str


_UNSAFE: Final = re.compile(
    rb"<!DOCTYPE|<!ENTITY|<script|<foreignObject|\son[a-z]+\s*=|javascript:", re.I
)
"""What an SVG to show may not hold: a doctype, script, foreign content, handlers, script links."""


def checked(rendered: bytes, as_: Format) -> bytes:
    """A render as it may be shown: a PNG by its signature, or an SVG that parses and runs nothing.

    Raises:
        ConversionFailed: If it is anything else, as `crashed`.
    """
    if as_ == "png":
        if not rendered.startswith(PNG):
            raise ConversionFailed("crashed", "the converter's PNG isn't one")
        return rendered
    if _UNSAFE.search(rendered):
        raise ConversionFailed("crashed", "the converter's SVG holds what can't be shown")
    try:
        root = ElementTree.fromstring(rendered)
    except ElementTree.ParseError as error:
        raise ConversionFailed("crashed", "the converter's SVG doesn't parse") from error
    if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
        raise ConversionFailed("crashed", "the converter's SVG isn't one")
    return rendered


def _png(said: str) -> bytes:
    """A one-pixel white PNG, with `said` as its description."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixel = zlib.compress(b"\x00\xff\xff\xff")
    text = b"Description\x00" + said.encode("latin-1", "replace")
    return (
        PNG
        + chunk(b"IHDR", header)
        + chunk(b"tEXt", text)
        + chunk(b"IDAT", pixel)
        + chunk(b"IEND", b"")
    )
