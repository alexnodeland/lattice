"""A deployment's brand kit, served: its files under its hash, its index, and its config block."""

import json
import re
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from grantr.grants import Grants
from portalr.brand.kit import Kit
from portalr.fastapi import Site
from portalr.fastapi.ui import IMMUTABLE, NO_CACHE, SVG_POLICY, UnbrandableIndex, branded
from portalr.invites import Invite
from tests.fastapi.conftest import Stack, app_for

EXAMPLES = Path(__file__).parents[2] / "src" / "portalr" / "brand" / "examples"
BRANDED = Site(
    supabase_url="https://project.supabase.co",
    supabase_key="sb_publishable_x",
    brand=EXAMPLES / "nightshade",
)


INDEX = (
    '<!doctype html>\n<html lang="en">\n  <head>\n    <title>portalr</title>\n'
    '    <link rel="stylesheet" href="/portalr/app/assets/index.css">\n  </head>\n</html>\n'
)


@pytest.fixture
def built(ui: Path) -> Path:
    """Both UIs built, each with a whole index: a title and the end of its head."""
    for name in ("app", "admin"):
        (ui / name).mkdir(exist_ok=True)
        (ui / name / "index.html").write_text(INDEX)
    return ui


@pytest.fixture
async def branded_client(
    grants: Grants, stack: Stack, invite: Invite, built: Path
) -> AsyncIterator[httpx.AsyncClient]:
    app = app_for(grants, stack.readers(), invite, built, site=BRANDED)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        yield client


def kit() -> Kit:
    assert BRANDED.kit is not None
    return BRANDED.kit


async def test_the_kits_stylesheet_is_served_under_its_hash_for_good(
    branded_client: httpx.AsyncClient,
) -> None:
    response = await branded_client.get(f"/brand/{kit().hash}/brand.css")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/css; charset=utf-8"
    assert response.headers["cache-control"] == IMMUTABLE
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "--accent: light-dark(#0f6e6a, #7fd8cf);" in response.text


async def test_a_mark_is_served_as_an_svg_that_can_do_nothing_but_draw(
    branded_client: httpx.AsyncClient,
) -> None:
    response = await branded_client.get(f"/brand/{kit().hash}/assets/mark-light.svg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["content-security-policy"] == SVG_POLICY


@pytest.mark.parametrize(
    "path",
    ["brand.json", "tokens.light.json", "%2e%2e/brand.json", "assets%2F..%2Fbrand.json", "x.css"],
)
async def test_only_what_the_kit_serves_is_served(
    branded_client: httpx.AsyncClient, path: str
) -> None:
    response = await branded_client.get(f"/brand/{kit().hash}/{path}")
    assert response.status_code == 404


async def test_a_head_request_and_the_referrer_policy(branded_client: httpx.AsyncClient) -> None:
    response = await branded_client.head(f"/brand/{kit().hash}/brand.css")
    assert response.status_code == 200
    assert response.headers["referrer-policy"] == "no-referrer"


async def test_another_hash_is_not_found(branded_client: httpx.AsyncClient) -> None:
    response = await branded_client.get("/brand/0000000000000000/brand.css")
    assert response.status_code == 404


async def test_without_a_kit_nothing_is_served(client: httpx.AsyncClient) -> None:
    response = await client.get("/brand/0000000000000000/brand.css")
    assert response.status_code == 404


async def test_the_index_has_the_kit_before_the_first_paint(
    branded_client: httpx.AsyncClient,
) -> None:
    response = await branded_client.get("/app/threads/thr_1")
    assert response.status_code == 200
    assert response.headers["cache-control"] == NO_CACHE
    assert re.fullmatch(r'"[0-9a-f]{32}"', response.headers["etag"])
    base = f"/portalr/brand/{kit().hash}/"
    assert "<title>Nightshade</title>" in response.text
    assert f'<link rel="stylesheet" href="{base}brand.css" />' in response.text
    assert f'<link rel="icon" href="{base}assets/favicon.png" />' in response.text
    # After the UI's own stylesheet, so the kit's tokens are the page's.
    assert response.text.index("index.css") < response.text.index("brand.css")
    assert 'media="(prefers-color-scheme: light)" content="#f4f7f7"' in response.text
    assert 'media="(prefers-color-scheme: dark)" content="#0f1717"' in response.text


async def test_the_index_by_its_name_is_branded_too(branded_client: httpx.AsyncClient) -> None:
    response = await branded_client.get("/app/index.html")
    assert "<title>Nightshade</title>" in response.text


@pytest.mark.parametrize("asked", ["{tag}", "W/{tag}", '"other", {tag}', "*"])
async def test_an_unchanged_index_is_not_sent_again(
    branded_client: httpx.AsyncClient, asked: str
) -> None:
    first = await branded_client.get("/app/")
    header = asked.format(tag=first.headers["etag"])
    again = await branded_client.get("/app/", headers={"If-None-Match": header})
    assert again.status_code == 304
    assert again.content == b""


async def test_another_tag_gets_the_index(branded_client: httpx.AsyncClient) -> None:
    again = await branded_client.get("/app/", headers={"If-None-Match": '"other"'})
    assert again.status_code == 200


async def test_config_carries_the_kits_block(branded_client: httpx.AsyncClient) -> None:
    body = (await branded_client.get("/config.json")).json()
    assert body["brand"] == {
        "hash": kit().hash,
        "identity": {"product": "Nightshade", "app": "Nightshade", "admin": "Nightshade admin"},
        "copy": {"tagline": "Ask, and it is drafted.", "signIn": "Sign in to Nightshade"},
        "stylesheet": f"brand/{kit().hash}/brand.css",
        "mark": {
            "light": f"brand/{kit().hash}/assets/mark-light.svg",
            "dark": f"brand/{kit().hash}/assets/mark-dark.svg",
        },
        "favicon": f"brand/{kit().hash}/assets/favicon.png",
    }


async def test_without_a_kit_config_says_none(client: httpx.AsyncClient) -> None:
    assert (await client.get("/config.json")).json()["brand"] is None


def test_admin_is_named_for_admin() -> None:
    page = branded(INDEX, kit(), "admin")
    assert "<title>Nightshade admin</title>" in page
    assert page.index("brand.css") < page.index("</head>")


def test_a_hostile_name_is_escaped_and_never_read_as_a_pattern(tmp_path: Path) -> None:
    hostile = tmp_path / "hostile"
    shutil.copytree(EXAMPLES / "nightshade", hostile)
    data = json.loads((hostile / "brand.json").read_text())
    data["identity"]["app"] = 'AC\\DC \\1 </title><script>"&'
    (hostile / "brand.json").write_text(json.dumps(data))
    site = Site(
        supabase_url="https://p.supabase.co", supabase_key="sb_publishable_x", brand=hostile
    )
    assert site.kit is not None
    page = branded(INDEX, site.kit, "app")
    assert "<title>AC\\DC \\1 &lt;/title&gt;&lt;script&gt;&quot;&amp;</title>" in page
    assert page.count("<title>") == 1


@pytest.mark.parametrize(
    "index",
    [
        "<!doctype html><title>x</title>",
        "<head></head>",
        "<head><!-- <title>x</title> --><title>y</title></head>",
        "<head><title>x</title><script>'</head>'</script></head>",
    ],
)
def test_an_index_the_kit_cant_be_put_in_fails_the_start(index: str) -> None:
    with pytest.raises(UnbrandableIndex):
        branded(index, kit(), "app")


def test_a_kit_with_a_fault_fails_the_start_with_every_fault() -> None:
    with pytest.raises(ValueError, match="isn't one portalr can serve"):
        Site(
            supabase_url="https://p.supabase.co",
            supabase_key="sb_publishable_x",
            brand=Path("/nope"),
        )
