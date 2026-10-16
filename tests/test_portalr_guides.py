"""portalr's guides say what portalr does: their example runs, and their facts are the code's.

The getting-started page's Python blocks run in order, in one coroutine, so that a later block
sees what an earlier one made; a block titled "Illustrative" needs a sign-in and is left out. The
rest of what the guides state, which is the code's to say, is held here: the keys of
``config.json``, the actions of portalr's catalog, the limits and the lists a reader withholds by,
the fields of the record an operator's links leave, and that every route of both UIs is in the
architecture page and every guide is in the section's navigation.
"""

import json
import logging
import re
import runpy
import textwrap
from pathlib import Path

import pytest

from grantr.core import User
from portalr.access import record_links
from portalr.actions import ACTIONS
from portalr.fastapi.site import Surfaces
from portalr.readers import Readers
from portalr.readers.loki import DEADLINE, LEVELS, MOST_HOURS
from portalr.readers.query import MOST_DAYS
from portalr.readers.tempo import MOST_NAME, MOST_SPANS

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
    assert len(code) == 3
    body = textwrap.indent("\n".join(code), "    ")
    script = tmp_path / "example.py"
    script.write_text(
        f"import asyncio\n\n\nasync def example():\n{body}\n\nasyncio.run(example())\n"
    )
    runpy.run_path(str(script), run_name="__main__")


def table_keys(page: str, heading: str) -> list[str]:
    """The first cell of each row of the table under a heading, without its backticks."""
    section = text(page).split(heading, 1)[1]
    rows = []
    for line in section.splitlines()[1:]:
        if line.startswith("#") and rows:
            break
        if line.startswith("| ") and not line.startswith(("| Key", "| Action", "|---")):
            rows.append(line.split("|")[1].strip().strip("`"))
    return rows


def test_config_json_is_what_the_page_says() -> None:
    keys = table_keys("getting-started.md", "### `config.json`")
    assert keys == ["supabase.url", "supabase.key", "surfaces", "readers"]
    page = text("getting-started.md")
    for field, default in Surfaces().model_dump().items():
        assert (
            f"`{field}` (default `{default}`" in page
            or (field == "grantr" and '`grantr` (`""`' in page)
            or (f"`{field}` (`{default}`" in page)
        ), field
    for tool in Readers().configured():
        assert f"`{tool}`" in page, tool


def test_the_actions_are_those_the_page_names() -> None:
    assert sorted(
        table_keys("getting-started.md", "## Name portalr's actions to grantr")
    ) == sorted(ACTIONS)


def test_the_limits_the_privacy_guide_states_are_the_codes() -> None:
    privacy = text("guides/privacy.md")
    admin = text("guides/admin.md")
    assert f"at most {MOST_HOURS} hours" in privacy
    assert f"{MOST_SPANS:,} spans" in admin
    assert f"cut to {MOST_NAME} characters" in privacy
    assert f"{MOST_DAYS} days" in admin
    assert "ten seconds" in privacy
    assert DEADLINE == 10
    # The levels a record may be shown at.
    for level in LEVELS:
        assert f"`{level}`" in privacy, level


def test_the_record_the_runbook_shows_has_the_fields_the_code_writes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    (example,) = [code for _info, code in blocks("guides/operators.md", "json")]
    with caplog.at_level(logging.INFO, logger="portalr.access"):
        record_links(User(id="ops"), kinds=["trace"], tenant=None, tools=["grafana"])
    (written,) = [json.loads(each.getMessage()) for each in caplog.records]
    assert sorted(json.loads(example)) == sorted(written)
    assert written["event"] == json.loads(example)["event"]


ROUTE = re.compile(r"^  '(/[^']*)': typeof ", flags=re.MULTILINE)


def documented(path: str, architecture: str) -> bool:
    """Whether the architecture page names a route: whole, or as the tail of one it lists with
    its parent, such as ``/traces/$trace`` under ``/t/$tenant/traces``."""
    parts = path.rstrip("/").split("/")
    tails = ["/".join(parts[-count:]) for count in range(1, len(parts) + 1)]
    return any(f"`{tail}`" in architecture or f"`/{tail}`" in architecture for tail in tails)


@pytest.mark.parametrize("ui", ["app", "admin"])
def test_every_route_of_a_ui_is_in_the_architecture_page(ui: str) -> None:
    tree = (ROOT / "packages" / "portalr" / "web" / ui / "src" / "routeTree.gen.ts").read_text()
    full_paths = sorted(set(ROUTE.findall(tree.split("FileRoutesByFullPath")[1].split("}")[0])))
    architecture = text("architecture.md")
    # A layout route, such as Access's, is documented by the routes inside it.
    missing = [
        path
        for path in full_paths
        if not documented(path, architecture)
        and not any(
            other.startswith(path.rstrip("/") + "/") and documented(other, architecture)
            for other in full_paths
        )
    ]
    assert not missing, f"{ui}: add to architecture.md: {missing}"


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
