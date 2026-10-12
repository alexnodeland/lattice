"""grantr's guides say what grantr does: their in-memory examples run, and the matrix is current.

The guides' examples name artifactr's and reflexr's catalogs, so this test, which sees every
package, runs them. A block titled "Illustrative" needs a database or a sign-in, and is left out.
"""

import re
import runpy
import textwrap
from pathlib import Path

import pytest

from artifactr.workspace import ACTIONS as ARTIFACTR
from grantr.testing import matrix
from reflexr.workspace import ACTIONS as REFLEXR

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs" / "grantr"
BLOCK = re.compile(r"```python([^\n]*)\n(.*?)```", flags=re.DOTALL)

TENANT = """\
from artifactr.workspace import ACTIONS as ARTIFACTR
from reflexr.workspace import ACTIONS as REFLEXR

from grantr import Grants, InMemoryStorage, User

grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR, REFLEXR])
await grants.first_operator("root")
await grants.create_tenant("acme", owner="alice", by=User(id="root"))
"""
"""What a guide's snippets assume: a tenant, acme, that Alice owns."""


def examples(page: Path) -> list[str]:
    """The page's Python blocks, but the illustrative ones."""
    blocks = BLOCK.findall(page.read_text())
    return [code for info, code in blocks if "Illustrative" not in info]


def run(tmp_path: Path, blocks: list[str]) -> None:
    """Run the blocks in order, in one coroutine, so later ones see what earlier ones made."""
    body = textwrap.indent("\n".join(blocks), "    ")
    script = tmp_path / "example.py"
    script.write_text(
        f"import asyncio\n\n\nasync def example():\n{body}\n\nasyncio.run(example())\n"
    )
    runpy.run_path(str(script), run_name="__main__")


def test_getting_started_runs(tmp_path: Path) -> None:
    whole, *snippets = examples(DOCS / "getting-started.md")
    script = tmp_path / "getting_started.py"
    script.write_text(whole)
    runpy.run_path(str(script), run_name="__main__")
    run(tmp_path, [TENANT, *snippets])


@pytest.mark.parametrize("guide", ["roles-and-grants", "restricted-items", "keys"])
def test_a_guides_examples_run(tmp_path: Path, guide: str) -> None:
    run(tmp_path, [TENANT, *examples(DOCS / "guides" / f"{guide}.md")])


def test_the_readmes_quick_start_runs(tmp_path: Path) -> None:
    run(tmp_path, examples(ROOT / "packages" / "grantr" / "README.md"))


def test_the_matrix_page_is_current() -> None:
    page = (DOCS / "guides" / "matrix.md").read_text()
    assert page.endswith(matrix([ARTIFACTR, REFLEXR])), "regenerate it: see the page's first lines"
