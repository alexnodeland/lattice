"""Probe the diagrams worker, from the application's side of its relay: scripts/check-files runs it.

Usage: python -I _diagrams_probe.py URL   (WORKER_TOKEN in the environment)

It runs in a native file's worker's image, which has artifactr and so its converter, the one the
application calls (stackr ADR-0049), and checks, through the worker's relay:

- a call without the worker's token is refused
- Mermaid becomes elements: a flowchart, with CJK words, as shapes; a Gantt chart as a PNG
- skeletons become elements, with the ids they were given
- a diagram renders as an SVG and as a PNG, each as artifactr checks a render: the SVG holds no
  link out and no face but those it embeds
- a diagram at its limit, 2,000 elements, renders as both within the deadline
- Mermaid that doesn't parse is `invalid`, and a diagram past the limit is `too_large`

Each check prints `ok: ...` or `FAIL: ...`; it exits 1 if any failed.
"""

import asyncio
import hashlib
import os
import sys
import time
from collections.abc import Awaitable

import httpx
from artifactr.excalidraw import ConversionFailed, Diagram, DiagramFile, Element, WorkerConverter
from artifactr.excalidraw.converter import Skeleton
from artifactr.excalidraw.types import MAX_ELEMENTS

DEADLINE = 10.0
failed = False


def report(passed: bool, what: str) -> None:
    global failed
    print(f"{'ok' if passed else 'FAIL'}: {what}", flush=True)
    failed |= not passed


def scene(model: Element, count: int) -> dict[str, Element]:
    """`count` copies of an element, on a grid, each its own."""
    data = model.model_dump(mode="json", by_alias=True)
    return {
        f"e{n}": Element.model_validate(
            {**data, "id": f"e{n}", "x": (n % 50) * 120, "y": (n // 50) * 90, "boundElements": []}
        )
        for n in range(count)
    }


async def refused(what: str, reason: str, call: Awaitable[object]) -> None:
    try:
        await call
    except ConversionFailed as failure:
        report(failure.reason == reason, f"{what}: {failure.reason}, {failure}")
    else:
        report(False, f"{what}: drawn")


async def main(url: str) -> None:
    async with httpx.AsyncClient(base_url=url) as anyone:
        reply = await anyone.post("/mermaid", json={"source": "flowchart LR\n  A --> B"})
        report(
            reply.status_code == 401, f"a call without the token is refused ({reply.status_code})"
        )
    worker = WorkerConverter.at(url, token=os.environ["WORKER_TOKEN"])
    try:
        flow = await worker.mermaid("flowchart LR\n  API -- reads --> DB\n  DB --> 中文")
        kinds = sorted({e.type for e in flow.elements})
        report({"rectangle", "arrow", "text"} <= set(kinds), f"a flowchart is drawn: {kinds}")
        gantt = await worker.mermaid(
            "gantt\n  title Launch\n  section A\n  Build :a1, 2026-01-01, 3d"
        )
        pictures = [file.media_type for file in gantt.files.values()]
        report(pictures == ["image/png"], f"a Gantt chart is drawn as a picture: {pictures}")
        boxes = await worker.skeletons(
            [Skeleton(type="rectangle", id="box", label="Box"), Skeleton(type="ellipse", id="o")]
        )
        report({"box", "o"} <= {e.id for e in boxes.elements}, "skeletons keep their ids")

        files: dict[str, DiagramFile] = {}
        held: dict[str, bytes] = {}
        elements = {e.id: e for e in [*flow.elements, *boxes.elements]}
        for key, file in gantt.files.items():
            data = file.content()
            digest = hashlib.sha256(data).hexdigest()
            files[digest] = DiagramFile(sha256=digest, size=len(data), media_type=file.media_type)
            held[digest] = data
            for element in gantt.elements:
                fields = element.model_dump(mode="json", by_alias=True)
                if fields.get("fileId") == key:
                    fields |= {"fileId": digest, "y": 400}
                elements[element.id] = Element.model_validate(fields)
        drawn = Diagram(name="probe", elements=elements, files=files)
        for as_ in ("svg", "png"):
            began = time.monotonic()
            rendered = await worker.render(drawn, held, as_=as_)
            took = time.monotonic() - began
            report(
                took < DEADLINE,
                f"a diagram renders as a checked {as_}: {len(rendered)} bytes, {took:.2f}s",
            )
        svg = (await worker.render(drawn, held, as_="svg")).decode()
        report(
            "esm.sh" not in svg
            and "http" not in svg.split("<svg", 1)[1].replace("http://www.w3.org/", ""),
            "the SVG names nothing out of it",
        )

        full = Diagram(name="full", elements=scene(boxes.elements[0], MAX_ELEMENTS))
        for as_ in ("svg", "png"):
            began = time.monotonic()
            rendered = await worker.render(full, {}, as_=as_)
            took = time.monotonic() - began
            report(
                took < DEADLINE,
                f"{MAX_ELEMENTS} elements render as a {as_} within {DEADLINE:g}s: {took:.2f}s",
            )

        await refused(
            "Mermaid that doesn't parse", "invalid", worker.mermaid("flowchart LR\n  A -->")
        )
        past = Diagram.model_construct(
            name="past", elements=scene(boxes.elements[0], MAX_ELEMENTS + 1), files={}
        )
        await refused("a diagram past its limit", "too_large", worker.render(past, {}, as_="svg"))
    finally:
        await worker.aclose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
    sys.exit(1 if failed else 0)
