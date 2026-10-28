"""portalr's guides say what portalr does: their example runs, and their facts are the code's.

The getting-started page's Python blocks run in order, in one coroutine, so that a later block
sees what an earlier one made; a block titled "Illustrative" needs a sign-in and is left out. The
rest of what the guides state, which is the code's to say, is held here: the keys of
``config.json``, the actions of portalr's catalog, the limits and the lists a reader withholds by,
the fields of the record an operator's links leave, who sees whose email and how long it is kept,
the look the UIs' tokens give (a compact admin, status colours, colour-blind mode as a hook that
nothing sets yet), the stack's spend key and sign-in allow-list, and that every route of both UIs
is in the architecture page and every guide is in the section's navigation.
"""

import asyncio
import dataclasses
import inspect
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
from jwt.algorithms import ECAlgorithm
from starlette.requests import HTTPConnection

from artifactr.workspace import ACTIONS as ARTIFACTR
from grantr.core import User
from grantr.core.roles import Catalog
from grantr.fastapi import Caller, Unauthorized
from portalr.access import record_links
from portalr.actions import ACTIONS
from portalr.fastapi import portalr_router
from portalr.fastapi.router import MAX_PEOPLE
from portalr.fastapi.site import Surfaces
from portalr.people import SupabasePeople
from portalr.readers import LogQuery, Readers
from portalr.readers import loki as loki_reader
from portalr.readers import tempo as tempo_reader
from portalr.readers.loki import LEVELS, MOST_HOURS, MOST_SAME_INSTANT
from portalr.readers.query import MOST_DAYS
from portalr.readers.tempo import MOST_NAME, MOST_SPANS
from reflexr.workspace import ACTIONS as REFLEXR

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs" / "portalr"
WEB = ROOT / "packages" / "portalr" / "web"
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
        if line.startswith("| ") and not line.startswith(
            ("| Key", "| Action", "| Argument", "|---")
        ):
            first, *rest = [cell.strip() for cell in line.strip("|").split("|")]
            rows[first.strip("`")] = " ".join(rest)
    return rows


def test_config_json_is_what_the_page_says() -> None:
    rows = table_rows("getting-started.md", "### `config.json`")
    assert list(rows) == [
        "supabase.url",
        "supabase.key",
        "surfaces",
        "readers",
        "people",
        "editors",
        "apps",
        "origin",
        "aliases",
        "brand",
    ]
    for field, default in Surfaces().model_dump().items():
        shown = "null" if default is None else default or chr(34) * 2
        assert f"`{field}` (default `{shown}`" in rows["surfaces"], field
    for tool in Readers().configured():
        assert f"`{tool}`" in rows["readers"], tool


def test_the_routers_arguments_are_those_the_page_names() -> None:
    rows = table_rows("getting-started.md", "## Mount the router")
    keyword = [
        name
        for name, parameter in inspect.signature(portalr_router).parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    ]
    # Every argument but ``ui``, which only a test passes, in the order the router takes them.
    assert list(rows) == [name for name in keyword if name != "ui"]
    assert "SupabasePeople(url=, secret_key=)" in rows["people"]
    assert {"url", "secret_key"} <= set(inspect.signature(SupabasePeople).parameters)


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


def test_who_sees_whose_email_and_for_how_long_is_the_codes() -> None:
    privacy = text("guides/privacy.md")
    assert f"at most {MAX_PEOPLE} ids" in privacy
    defaults = {each.name: each.default for each in dataclasses.fields(SupabasePeople)}
    assert defaults["size"] == 2048
    assert "at most 2,048 ids" in privacy
    assert (defaults["found_for"], defaults["missing_for"], defaults["failed_for"]) == (300, 60, 5)
    assert "an email for five minutes, an id with no email for one minute" in privacy
    assert "a failed read for five seconds" in privacy
    people = (ROOT / "packages" / "portalr" / "src" / "portalr" / "people.py").read_text()
    assert "_MOST_RETRY_AFTER: Final = 60.0" in people
    assert "up to a minute" in privacy
    # The browser's cache, and the short id a person is shown by without an email.
    client = (WEB / "client" / "src" / "people.ts").read_text()
    assert "const SHORT = 8;" in client
    assert "first eight characters" in text("getting-started.md")
    assert "first eight characters" in text("guides/admin.md")
    queries = (WEB / "client" / "src" / "queries.ts").read_text()
    people_query = queries.split("people: (tenant: string | null, ids: readonly string[]) =>\n")[2]
    assert "staleTime: 5 * 60_000,\n          gcTime: 5 * 60_000," in people_query
    assert "query cache's memory for five minutes" in privacy
    openapi = json.loads(
        (ROOT / "packages" / "portalr" / "schemas" / "portalr.openapi.json").read_text()
    )
    assert "/portalr/v1/people" in openapi["paths"]


def test_the_deployment_audit_shows_tenant_creations_as_the_runbook_says() -> None:
    audit = (WEB / "admin" / "src" / "audit.ts").read_text()
    assert 'case "deployment_tenant_created":' in audit
    assert "created the tenant ${event.tenant}, owned by" in audit
    runbook = text("guides/operators.md")
    assert "`deployment_tenant_created`" in runbook
    assert '"created the tenant acme, owned by …"' in runbook


def test_the_look_the_guides_describe_is_the_kits() -> None:
    tokens = (WEB / "ui" / "src" / "tokens.css").read_text()
    base = (WEB / "ui" / "src" / "base.css").read_text()
    shell = (WEB / "ui" / "src" / "rail-shell.tsx").read_text()
    admin = text("guides/admin.md")
    # Admin is compact, and the app is not: 2.25rem and 3rem rows, at 16px to the rem.
    assert 'data-density={ui === "admin" ? "compact" : undefined}' in shell
    assert re.search(r"\[data-density=\"compact\"\] \{\n  --row-height: 2\.25rem;", base)
    assert "  --row-height: 3rem;" in tokens
    assert "rows are 36px high, where the app's are 48px" in admin
    # Status colours: a red and a gold, with a shape and a word.
    assert "--status-failed:" in tokens
    assert "--status-warn:" in tokens
    run_list = (WEB / "ui" / "src" / "run-list.tsx").read_text()
    assert 'dead_lettered: ["failed", "Dead-lettered"]' in run_list
    assert 'retrying: ["retrying", "Retrying"]' in run_list
    home = (WEB / "admin" / "src" / "home.ts").read_text()
    assert "max * 0.8" in home
    assert 'word: "Near budget"' in home
    assert 'word: "Over budget"' in home
    assert "**Near budget** at 80% of it and **Over budget** past it" in admin
    assert "Show the figures" in (WEB / "ui" / "src" / "chart.tsx").read_text()
    assert "**Show the figures**" in admin


def test_colour_blind_mode_is_a_setting_of_the_browser_in_the_account_menu() -> None:
    """The guides say where the setting lives, and the code is where they say."""
    ui = WEB / "ui"
    assert "[data-cvd] {" in (ui / "src" / "base.css").read_text()
    hook = (ui / "src" / "colour-blind.ts").read_text()
    assert 'key: "portalr-colour-blind"' in hook
    assert "dataset.cvd" in hook
    assert "localStorage" in (ui / "src" / "stored-setting.ts").read_text()
    assert "portalr-colour-blind" in (ui / "public" / "scheme.js").read_text()
    menu = (ui / "src" / "account-menu.tsx").read_text()
    assert "Colour-blind friendly charts" in menu
    assert "Menu.CheckboxItem" in menu
    for guide in ("guides/admin.md", "guides/app.md"):
        assert "**Colour-blind friendly charts** is a switch in the account menu" in text(guide), (
            guide
        )
        assert "setting of this browser" in text(guide), guide
        assert "local storage" in text(guide), guide
        assert "control for colour-blind mode" not in text(guide), guide
        assert "nothing in the ui sets it" not in text(guide).lower(), guide
    assert "colour-blind mode" not in text("index.md").lower().split("not built yet")[-1]


def test_the_stacks_spend_key_and_sign_in_are_what_the_runbook_says() -> None:
    runbook = text("guides/operators.md")
    script = (ROOT / "packages" / "stackr" / "scripts" / "create-portal-key").read_text()
    (listed,) = re.findall(r"^ROUTES = (\[.*\])$", script, flags=re.MULTILINE)
    routes = json.loads(listed)
    assert ", ".join(f"`{route}`" for route in routes[:-1]) + f" and `{routes[-1]}`" in runbook
    caddy = (ROOT / "packages" / "stackr" / "deploy" / "host" / "Caddyfile").read_text()
    allowed = re.findall(r"method (\w+)\n\s+path (/auth/v1/\w+)", caddy)
    assert len(allowed) == 3
    for method, path in allowed:
        assert f"`{method} {path}`" in runbook, (method, path)
    # The reason a single host's invitations give, which the template's portal writes.
    template = ROOT / "packages" / "stackr" / "template" / "src" / "{{ package_name }}"
    (portal,) = template.glob("*portal.py*.jinja")
    (reason,) = re.findall(r'InviteFailed\("(invitations need [^"]+)"\)', portal.read_text())
    assert f'"{reason}"' in runbook


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
            json.loads(ECAlgorithm.to_jwk(key.public_key())) | {"alg": "ES256"}
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


def test_the_template_names_people_as_the_guides_say() -> None:
    """stackr's template passes ``people=`` with what invitations need; the guides say so."""
    template = ROOT / "packages" / "stackr" / "template" / "src" / "{{ package_name }}"
    portal = (template / "{% if use_portal %}portal.py{% endif %}.jinja").read_text()
    assert "people=people(self._settings, self._clients)" in portal
    assert "url, key = settings.portal.auth_url, settings.auth.service_role_key" in portal
    assert 'SupabasePeople(url=url.rstrip("/"), secret_key=key, client=client)' in portal
    assert "doesn't pass yet" not in text("guides/privacy.md")
    assert "passes it whenever the application has the gateway's address" in text(
        "guides/privacy.md"
    )


def test_the_size_budgets_are_the_adrs() -> None:
    """ADR-0040 states the ceilings in size-budget.json, and sizes they are a little above."""
    budgets = json.loads((ROOT / "packages" / "portalr" / "size-budget.json").read_text())
    adr = text("adr/0040-scenarios-against-a-generated-application-and-size-budgets.md")
    assert sorted(budgets) == ["admin", "app"]
    measures = ("initial", "total", "largest")
    for measure in measures:
        assert f"`{measure}`" in adr, measure
    sizes = re.search(r"Sizes at the time: (.+?)\. Ceilings: (.+?)\.(?:\s|$)", adr)
    assert sizes, "the ADR states the sizes and the ceilings"
    for ui in budgets:
        stated = {}
        for label, line in zip(("sizes", "ceilings"), sizes.groups(), strict=True):
            found = re.search(rf"{ui} ([\d.]+) / ([\d.]+) / ([\d.]+) kB", line)
            assert found, f"{ui}'s {label}"
            stated[label] = [round(float(n) * 1000) for n in found.groups()]
        for measure, size, ceiling in zip(
            measures, stated["sizes"], stated["ceilings"], strict=True
        ):
            assert budgets[ui][measure] == ceiling, (ui, measure)
            assert size <= ceiling <= size * 1.25, (ui, measure)
