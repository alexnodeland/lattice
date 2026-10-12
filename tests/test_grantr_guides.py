"""grantr's guides say what grantr does: their first example runs, and the matrix is current.

The guides' examples name artifactr's and reflexr's catalogs, so this test, which sees every
package, runs them.
"""

import re
import runpy
from pathlib import Path

from artifactr.workspace import ACTIONS as ARTIFACTR
from grantr.testing import matrix
from reflexr.workspace import ACTIONS as REFLEXR

GUIDES = Path(__file__).parent.parent / "docs" / "grantr" / "guides"


def test_getting_starteds_example_runs(tmp_path: Path) -> None:
    guide = (GUIDES / "getting-started.md").read_text()
    [first, *_] = re.findall(r"```python\n(.*?)```", guide, flags=re.DOTALL)
    script = tmp_path / "example.py"
    script.write_text(first)
    runpy.run_path(str(script), run_name="__main__")


def test_the_matrix_page_is_current() -> None:
    page = (GUIDES / "matrix.md").read_text()
    assert page.endswith(matrix([ARTIFACTR, REFLEXR])), "regenerate it from grantr.testing.matrix"
