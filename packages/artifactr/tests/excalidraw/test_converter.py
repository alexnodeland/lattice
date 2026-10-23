"""The converter: the worker's client over HTTP, and the fake that draws without one."""

import base64
import json

import httpx
import pytest

from artifactr.excalidraw import ConversionFailed, FakeConverter, WorkerConverter
from artifactr.excalidraw.converter import (
    MAX_MERMAID,
    MAX_SKELETONS,
    Converted,
    ConvertedFile,
)
from tests.excalidraw.scenes import diagram, element

ONE = Converted(elements=[element("r1")]).model_dump_json(by_alias=True)


def _worker(
    reply: httpx.Response | Exception, seen: list[httpx.Request] | None = None
) -> WorkerConverter:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return WorkerConverter.at("http://worker", token="t0k3n", transport=httpx.MockTransport(handle))


async def test_the_worker_is_sent_each_call_with_its_token_and_its_deadline() -> None:
    seen: list[httpx.Request] = []
    worker = _worker(httpx.Response(200, content=ONE), seen)
    drawn = await worker.mermaid("flowchart LR\n  A --> B", deadline=3)
    await worker.skeletons([{"type": "rectangle"}])
    assert [e.id for e in drawn.elements] == ["r1"]
    assert seen[0].url.path == "/mermaid"
    assert seen[0].headers["authorization"] == "Bearer t0k3n"
    assert json.loads(seen[0].content) == {"source": "flowchart LR\n  A --> B", "deadline": 3}
    assert json.loads(seen[1].content)["skeletons"] == [{"type": "rectangle"}]
    await worker.aclose()


async def test_a_render_sends_the_diagram_and_its_images_and_gives_the_bytes() -> None:
    seen: list[httpx.Request] = []
    worker = _worker(httpx.Response(200, content=b"<svg/>"), seen)
    rendered = await worker.render(diagram(element("r1")), {"d": b"png"}, as_="svg")
    assert rendered == b"<svg/>"
    sent = json.loads(seen[0].content)
    assert (sent["as"], sent["files"]) == ("svg", {"d": base64.b64encode(b"png").decode()})
    assert sent["diagram"]["elements"]["r1"]["versionNonce"] == 10


@pytest.mark.parametrize(
    ("reply", "reason", "said"),
    [
        (httpx.Response(422, json={"reason": "invalid", "message": "line 2"}), "invalid", "line 2"),
        (
            httpx.Response(413, json={"reason": "too_large", "message": "x" * 900}),
            "too_large",
            "x" * 500,
        ),
        (httpx.Response(500, text="oops"), "crashed", "the converter answered 500"),
        (
            httpx.Response(200, text="not json"),
            "crashed",
            "the converter replied with something else",
        ),
        (httpx.ReadTimeout("slow"), "timeout", "the converter took more than 10s"),
        (httpx.ConnectError("down"), "crashed", "the converter couldn't be reached"),
    ],
)
async def test_every_failure_is_a_typed_one(
    reply: httpx.Response | Exception, reason: str, said: str
) -> None:
    with pytest.raises(ConversionFailed) as failed:
        await _worker(reply).mermaid("flowchart LR\n  A --> B")
    assert (failed.value.reason, str(failed.value)) == (reason, said)


async def test_what_is_past_a_limit_is_refused_before_it_is_sent() -> None:
    seen: list[httpx.Request] = []
    worker = _worker(httpx.Response(200, content=ONE), seen)
    with pytest.raises(ConversionFailed, match=f"at most {MAX_MERMAID}"):
        await worker.mermaid("x" * (MAX_MERMAID + 1))
    with pytest.raises(ConversionFailed, match=f"at most {MAX_SKELETONS}"):
        await worker.skeletons([{"type": "rectangle"}] * (MAX_SKELETONS + 1))
    assert seen == []


def test_an_image_is_its_base64_or_a_failure() -> None:
    assert (
        ConvertedFile(media_type="image/png", data=base64.b64encode(b"x").decode()).content()
        == b"x"
    )
    with pytest.raises(ConversionFailed, match="isn't base64"):
        ConvertedFile(media_type="image/png", data="%%%").content()


async def test_the_fake_draws_a_flowchart_with_labels_and_refuses_the_rest() -> None:
    fake = FakeConverter()
    drawn = await fake.mermaid("flowchart LR\n  API -- reads --> DB\n  DB --> API")
    said = diagram(*drawn.elements).render_for_agent()
    assert '"API" --"reads"--> ' in said
    assert '"DB" --> ' in said
    with pytest.raises(ConversionFailed, match="flowcharts alone"):
        await fake.mermaid("pie title Pets")
    with pytest.raises(ConversionFailed, match="not an edge"):
        await fake.mermaid("graph TD\n  A")
    with pytest.raises(ConversionFailed, match="no time"):
        await fake.mermaid("graph TD\n  A --> B", deadline=0)


async def test_the_fake_draws_skeletons_and_refuses_one_without_a_type_or_an_element() -> None:
    fake = FakeConverter()
    drawn = await fake.skeletons([{"type": "ellipse", "id": "e", "label": "Hi"}, {"type": "line"}])
    assert [e.type for e in drawn.elements] == ["ellipse", "text", "line"]
    with pytest.raises(ConversionFailed, match="names its type"):
        await fake.skeletons([{"x": 1}])
    with pytest.raises(ConversionFailed, match="not an element"):
        await fake.skeletons([{"type": "rectangle", "x": float("nan")}])


async def test_the_fake_renders_a_description() -> None:
    fake = FakeConverter()
    svg = await fake.render(diagram(element("r1")), {}, as_="svg")
    assert svg.startswith(b"<svg")
    png = await fake.render(diagram(element("r1")), {"d": b"x"}, as_="png")
    assert png.startswith(b"\x89PNG")
    assert b"(1 images)" in png
