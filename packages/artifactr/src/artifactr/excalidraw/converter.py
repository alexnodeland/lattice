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
from collections.abc import Mapping, Sequence
from typing import Annotated, Final, Literal, Protocol, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from artifactr.excalidraw.types import MAX_ELEMENTS, Diagram, Element

__all__ = [
    "DEADLINE",
    "MAX_MERMAID",
    "MAX_SKELETONS",
    "ConversionFailed",
    "Converted",
    "ConvertedFile",
    "Converter",
    "FakeConverter",
    "Format",
    "Reason",
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


class Converter(Protocol):
    """What draws and renders diagrams: Mermaid or skeletons into elements, a diagram into an image.

    Each call fails with [`ConversionFailed`][artifactr.excalidraw.converter.ConversionFailed]
    and never with anything else, within its deadline and a little more.
    """

    async def mermaid(self, source: str, *, deadline: float = DEADLINE) -> Converted:
        """Draw a Mermaid diagram: flowcharts, sequences, classes, ER and states as shapes."""
        ...

    async def skeletons(
        self, skeletons: Sequence[Mapping[str, JsonValue]], *, deadline: float = DEADLINE
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
        """Render a diagram, with the images it shows, as SVG or PNG."""
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
        reply = await self._post("/mermaid", {"source": source, "deadline": deadline}, deadline)
        return _converted(reply)

    async def skeletons(
        self, skeletons: Sequence[Mapping[str, JsonValue]], *, deadline: float = DEADLINE
    ) -> Converted:
        """Draw skeletons in the worker."""
        _within("the skeletons", len(skeletons), MAX_SKELETONS, "skeletons")
        sent = {"skeletons": [dict(each) for each in skeletons], "deadline": deadline}
        return _converted(await self._post("/skeletons", sent, deadline))

    async def render(
        self,
        diagram: Diagram,
        files: Mapping[str, bytes],
        *,
        as_: Format,
        deadline: float = DEADLINE,
    ) -> bytes:
        """Render a diagram in the worker."""
        sent = {
            "diagram": diagram.to_json(),
            "files": {key: base64.b64encode(data).decode() for key, data in files.items()},
            "as": as_,
            "deadline": deadline,
        }
        return (await self._post("/render", sent, deadline)).content

    async def _post(self, path: str, body: Mapping[str, object], deadline: float) -> httpx.Response:
        try:
            reply = await self._client.post(path, json=body, timeout=deadline + GRACE)
        except httpx.TimeoutException as error:
            raise ConversionFailed(
                "timeout", f"the converter took more than {deadline:g}s"
            ) from error
        except httpx.HTTPError as error:
            raise ConversionFailed("crashed", "the converter couldn't be reached") from error
        if reply.is_success:
            return reply
        raise _refused(reply)


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
            arrow = self._element(
                "arrow",
                None,
                startBinding={"elementId": ends[0].id},
                endBinding={"elementId": ends[1].id},
            )
            made.append(arrow)
            if label.strip():
                made.append(self._element("text", None, text=label.strip(), containerId=arrow.id))
        return Converted(elements=made)

    async def skeletons(
        self, skeletons: Sequence[Mapping[str, JsonValue]], *, deadline: float = DEADLINE
    ) -> Converted:
        """Draw each skeleton as its element, its label a text bound in it."""
        _in_time(deadline)
        _within("the skeletons", len(skeletons), MAX_SKELETONS, "skeletons")
        made: list[Element] = []
        for skeleton in skeletons:
            kind = skeleton.get("type")
            if not isinstance(kind, str) or not kind:
                raise ConversionFailed("invalid", "a skeleton names its type")
            fields = {k: v for k, v in skeleton.items() if k not in {"type", "label", "id"}}
            element = self._element(kind, skeleton.get("id"), **fields)
            made.append(element)
            if isinstance(label := skeleton.get("label"), str):
                made.append(self._element("text", None, text=label, containerId=element.id))
        return Converted(elements=made)

    async def render(
        self,
        diagram: Diagram,
        files: Mapping[str, bytes],
        *,
        as_: Format,
        deadline: float = DEADLINE,
    ) -> bytes:
        """A small SVG, or the PNG's signature and the same words, holding the description."""
        _in_time(deadline)
        said = json.dumps(f"{diagram.render_for_agent()} ({len(files)} images)")
        if as_ == "png":
            return b"\x89PNG\r\n\x1a\n" + said.encode()
        return f'<svg xmlns="http://www.w3.org/2000/svg"><desc>{said}</desc></svg>'.encode()

    def _node(self, nodes: dict[str, Element], made: list[Element], name: str) -> Element:
        if name not in nodes:
            nodes[name] = self._element("rectangle", None, x=len(nodes) * 200, y=0)
            made.append(nodes[name])
            made.append(self._element("text", None, text=name, containerId=nodes[name].id))
        return nodes[name]

    def _element(self, kind: str, given: JsonValue, **fields: JsonValue) -> Element:
        self._made += 1
        made = given if isinstance(given, str) else f"fake{self._made}"
        data: dict[str, JsonValue] = {
            "x": 0,
            "y": 0,
            "width": 160,
            "height": 80,
            **fields,
            "id": made,
            "type": kind,
            "version": 1,
            "versionNonce": int(hashlib.sha256(made.encode()).hexdigest()[:7], 16),
        }
        try:
            return Element.model_validate(data)
        except ValidationError as error:
            raise ConversionFailed(
                "invalid", f"not an element: {error.errors()[0]['msg']}"
            ) from error


def _in_time(deadline: float) -> None:
    if deadline <= 0:
        raise ConversionFailed("timeout", "no time was given to draw it")


def _within(what: str, size: int, most: int, unit: str) -> None:
    if size > most:
        raise ConversionFailed("too_large", f"{what} is {size} {unit}: at most {most}")


def _converted(reply: httpx.Response) -> Converted:
    try:
        return Converted.model_validate_json(reply.content)
    except ValidationError as error:
        raise ConversionFailed("crashed", "the converter replied with something else") from error


def _refused(reply: httpx.Response) -> ConversionFailed:
    try:
        said = _Refusal.model_validate_json(reply.content)
    except ValidationError:
        return ConversionFailed("crashed", f"the converter answered {reply.status_code}")
    return ConversionFailed(said.reason, said.message[:500])


class _Refusal(BaseModel):
    """What the worker says of a call it couldn't carry out."""

    reason: Reason
    message: str
