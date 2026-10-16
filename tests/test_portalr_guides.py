"""portalr's guides say what portalr does: their example runs, and their facts are the code's.

The getting-started page's Python blocks run in order, in one coroutine, so that a later block
sees what an earlier one made; a block titled "Illustrative" needs a sign-in and is left out. The
rest of what the guides state, which is the code's to say, is held here: the keys of
``config.json``, the actions of portalr's catalog, the limits and the lists a reader withholds by,
the fields of the record an operator's links leave, and that every route of both UIs is in the
architecture page and every guide is in the section's navigation.
"""

import asyncio
import json
import logging
import re
import runpy
import textwrap
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from starlette.requests import HTTPConnection

from artifactr.workspace import ACTIONS as ARTIFACTR
from grantr.core import User
from grantr.core.roles import Catalog
from grantr.fastapi import Caller, Unauthorized
from portalr.access import record_links
from portalr.actions import ACTIONS
from portalr.fastapi.site import Surfaces
from portalr.readers import LogQuery, Readers
from portalr.readers import loki as loki_reader
from portalr.readers import tempo as tempo_reader
from portalr.readers.loki import LEVELS, MOST_HOURS, MOST_SAME_INSTANT
from portalr.readers.query import MOST_DAYS
from portalr.readers.tempo import MOST_NAME, MOST_SPANS
from reflexr.workspace import ACTIONS as REFLEXR

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs" / "portalr"
BLOCK = re.compile(r"```(\w+)([^\n]*)\n(.*?)```", flags=re.DOTALL)
GUIDES = ("app", "admin", "operators", "privacy")


def text(page: str) -> str:
    return (DOCS / page).read_text()


def blocks(page: str, language: str) -> list[tuple[str, str]]:
    """The page's blocks of a language, as (what follows the language, the code)."""
    return [(info, code) for lang, info, code in BLOCK.findall(text(page)) if lang == language]


def test_getting_started_runs(tmp_path: Path) -> None:
    """The mounting, the config and the grants the page shows run, in order, as one example."""
    code = [
        code for info, code in blocks("getting-started.md", "python") if "Illustrative" not in info
    ]
    assert len(code) == 4
    body = textwrap.indent("\n".join(code), "    ")
    script = tmp_path / "example.py"
    script.write_text(
        f"import asyncio\n\n\nasync def example():\n{body}\n\nasyncio.run(example())\n"
    )
    runpy.run_path(str(script), run_name="__main__")


def table_rows(page: str, heading: str) -> dict[str, str]:
    """The table under a heading: each row's first cell, without its backticks, and its others."""
    section = text(page).split(heading, 1)[1]
    rows: dict[str, str] = {}
    for line in section.splitlines()[1:]:
        if line.startswith("#") and rows:
            break
        if line.startswith("| ") and not line.startswith(("| Key", "| Action", "|---")):
            first, *rest = [cell.strip() for cell in line.strip("|").split("|")]
            rows[first.strip("`")] = " ".join(rest)
    return rows


def test_config_json_is_what_the_page_says() -> None:
    rows = table_rows("getting-started.md", "### `config.json`")
    assert list(rows) == ["supabase.url", "supabase.key", "surfaces", "readers"]
    for field, default in Surfaces().model_dump().items():
        assert f"`{field}` (default `{default or chr(34) * 2}`" in rows["surfaces"], field
    for tool in Readers().configured():
        assert f"`{tool}`" in rows["readers"], tool


def test_the_actions_are_those_the_page_names() -> None:
    rows = table_rows("getting-started.md", "## Name portalr's actions to grantr")
    assert sorted(rows) == sorted(ACTIONS)
    assert "`owner` and `admin`" in rows["portalr:read_telemetry"]
    assert "`owner` and `admin`" in rows["portalr:read_spend"]
    assert "`operator`" in rows["portalr:read_deployment"]


def test_the_limits_the_guides_state_are_the_codes() -> None:
    privacy = text("guides/privacy.md")
    admin = text("guides/admin.md")
    assert f"at most {MOST_HOURS} hours" in privacy
    assert f"{MOST_SPANS:,} spans" in admin
    assert f"cut to {MOST_NAME} characters" in privacy
    assert f"{MOST_DAYS} days" in admin
    # Loki and Tempo each have ten seconds, and a log read gives at most a thousand records.
    assert "ten seconds" in privacy
    assert loki_reader.DEADLINE == tempo_reader.DEADLINE == 10
    assert "1,000 records" in privacy
    assert (
        LogQuery.model_validate(
            {
                "start": "2026-10-12T00:00:00Z",
                "end": "2026-10-12T01:00:00Z",
                "limit": 1000,
            }
        ).limit
        == 1000
    )
    assert MOST_SAME_INSTANT == 1000
    # The levels a record may be shown at.
    for level in LEVELS:
        assert f"`{level}`" in privacy, level


def test_reflexr_unreachable_is_said_after_the_ten_seconds_the_guide_names() -> None:
    runs = (ROOT / "packages" / "portalr" / "web" / "admin" / "src" / "runs.ts").read_text()
    assert re.search(r"export const PATIENCE = 10_000;", runs)
    assert "after ten seconds of connecting" in text("guides/admin.md")


def test_the_actions_the_admin_guide_names_are_held_by_the_roles_it_says() -> None:
    admin = text("guides/admin.md")
    named = set(re.findall(r"`((?:grantr|portalr|reflexr):[a-z_]+)`", admin.split("## Home")[0]))
    assert named >= {"portalr:read_telemetry", "portalr:read_spend", "grantr:read_audit"}
    roles = Catalog.of(ACTIONS, ARTIFACTR, REFLEXR).built_in
    owner, admin_role = roles[("tenant", "owner")], roles[("tenant", "admin")]
    assert named <= owner
    assert named <= admin_role
    assert "grantr:delete_tenant" in owner
    assert "grantr:delete_tenant" not in admin_role
    assert "lacks only deleting the tenant" in admin


def test_the_record_the_runbook_shows_is_what_the_code_writes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    (example,) = [json.loads(code) for _info, code in blocks("guides/operators.md", "json")]
    with caplog.at_level(logging.INFO, logger="portalr.access"):
        record_links(
            User(id=example["by"]["id"]),
            kinds=example["kinds"],
            tenant=example["tenant"],
            tools=example["tools"],
        )
    (written,) = [json.loads(each.getMessage()) for each in caplog.records]
    assert written == example


def verifier() -> Callable[[Any], Callable[[HTTPConnection], Any]]:
    """The guide's ``token_resolver``, as it is written, with what its block uses."""
    (code,) = [
        code
        for _info, code in blocks("getting-started.md", "python")
        if "def token_resolver" in code
    ]
    namespace = {
        "__name__": "guide",
        "HTTPConnection": HTTPConnection,
        "Caller": Caller,
        "Unauthorized": Unauthorized,
        "User": User,
    }
    exec(compile(code.split("# In your application")[0], "guide", "exec"), namespace)
    return namespace["token_resolver"]


class Published:
    """A key set that holds one public key, as ``jwt.PyJWKClient`` answers for a token's key."""

    def __init__(self, key: ec.EllipticCurvePrivateKey) -> None:
        self.key = jwt.PyJWK.from_dict(
            json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key())) | {"alg": "ES256"}
        )

    def get_signing_key_from_jwt(self, _token: str) -> jwt.PyJWK:
        return self.key


def request(token: str | None) -> HTTPConnection:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return HTTPConnection({"type": "http", "headers": headers, "query_string": b""})


def test_the_guides_token_resolver_accepts_supabases_tokens_and_no_others() -> None:
    asyncio.run(resolves())


async def resolves() -> None:
    resolver = verifier()(Published(key := ec.generate_private_key(ec.SECP256R1())))
    now = int(time.time())

    def token(signer: Any = key, **claims: Any) -> str:
        body = {"sub": "u_alice", "aud": "authenticated", "exp": now + 60} | claims
        return jwt.encode(body, signer, algorithm="ES256", headers={"kid": "k1"})

    assert (await resolver(request(token()))).subject == User(id="u_alice")
    for refused in (
        None,
        "not a token",
        token(exp=now - 60),
        token(aud="another"),
        token(signer=ec.generate_private_key(ec.SECP256R1())),
        jwt.encode({"sub": "u_alice", "aud": "authenticated", "exp": now + 60}, "s" * 32, "HS256"),
    ):
        with pytest.raises((Unauthorized, HTTPException)):
            await resolver(request(refused))
    socket = HTTPConnection(
        {
            "type": "websocket",
            "headers": [],
            "query_string": f"access_token={token()}".encode(),
        }
    )
    assert (await resolver(socket)).subject == User(id="u_alice")


ROUTE = re.compile(r"^  '(/[^']*)': typeof ", flags=re.MULTILINE)


def documented_routes(section: str, routes: set[str]) -> set[str]:
    """The routes a table of the architecture page names, by its rows' first cells.

    A row's first token is a whole path; a later one, such as ``/groups`` after
    ``/t/$tenant/access/members``, is read under the first's parent, or a parent of that, wherever
    it makes a route that exists.
    """
    found: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `/"):
            continue
        first_cell = line.split("|")[1]
        first, *others = re.findall(r"`(/[^`]*)`", first_cell)
        found.add(first.rstrip("/") or "/")
        parts = first.rstrip("/").split("/")
        for other in others:
            for depth in range(len(parts) - 1, 0, -1):
                candidate = "/".join(parts[:depth]) + other
                if candidate in routes:
                    found.add(candidate)
                    break
    return found


SECTIONS = {
    "app": ("## The app", "## The chat"),
    "admin": ("## admin", "## The kit's look"),
}


@pytest.mark.parametrize("ui", ["app", "admin"])
def test_every_route_of_a_ui_is_in_its_table_of_the_architecture_page(ui: str) -> None:
    tree = (ROOT / "packages" / "portalr" / "web" / ui / "src" / "routeTree.gen.ts").read_text()
    full_paths = set(ROUTE.findall(tree.split("FileRoutesByFullPath")[1].split("}")[0]))
    routes = {path.rstrip("/") or "/" for path in full_paths}
    start, end = SECTIONS[ui]
    section = text("architecture.md").split(start, 1)[1].split(end, 1)[0]
    found = documented_routes(section, routes)
    # A layout route, such as Access's, is documented by the routes inside it.
    missing = [
        path
        for path in sorted(routes)
        if path not in found and not any(other.startswith(path + "/") for other in found)
    ]
    assert not missing, f"{ui}: add to the architecture page's table: {missing}"
    assert found <= routes, sorted(found - routes)


def test_every_guide_is_in_the_navigation() -> None:
    nav = text(".nav.yml")
    assert "getting-started.md" in nav
    for guide in GUIDES:
        assert f"guides/{guide}.md" in nav, guide
        assert (DOCS / "guides" / f"{guide}.md").exists()


def test_every_decision_record_is_in_the_navigation() -> None:
    nav = text(".nav.yml")
    records = sorted(path.name for path in (DOCS / "adr").glob("0*.md"))
    assert [name for name in records if f"adr/{name}" not in nav] == []
