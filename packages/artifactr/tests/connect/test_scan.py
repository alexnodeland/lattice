"""The scan of an agent's code: what it shows the approver, and that it is only advisory."""

import pytest

from artifactr.connect import BLENDER, FREECAD, scan


@pytest.mark.parametrize(
    ("code", "found"),
    [
        ("import os, math", ["line 1: imports os"]),
        ("import os.path", ["line 1: imports os.path"]),
        ("from subprocess import run", ["line 1: imports from subprocess"]),
        ("from urllib.request import urlopen", ["line 1: imports from urllib.request"]),
        ("x = 1\nopen('/etc/passwd')", ["line 2: calls open()"]),
        ("exec('1')", ["line 1: calls exec()"]),
        ("__import__('os')", ["line 1: calls __import__()"]),
        ("getattr(o, name)", ["line 1: calls getattr() with a name made at run time"]),
        ("getattr(o)", ["line 1: calls getattr() with a name made at run time"]),
        ("().__class__.__bases__", ["line 1: reaches __bases__", "line 1: reaches __class__"]),
        ("while True:\n    pass", ["line 1: loops with no end of its own"]),
        ("while 1:\n    pass", ["line 1: loops with no end of its own"]),
        ("def f(:", ["line 1: it isn't Python that parses (invalid syntax)"]),
        # Nested past what one interpreter's parser takes, or past the scan's own bound where
        # another's parses it: a finding in every version either way.
        (
            "-" * 200_000 + "1",
            ["it can't be analysed: it nests too deeply, or the parser refuses it"],
        ),
        (
            "a" + ".b" * 200_000,
            ["it can't be analysed: it nests too deeply, or the parser refuses it"],
        ),
        ("a" + ".b" * 300, ["it can't be analysed: it nests too deeply, or the parser refuses it"]),
        ("a" + ".b" * 150, []),
        (
            "x = 1\0",
            [
                "line 1: holds an unseen character, U+0000",
                "it isn't Python that parses (source code string cannot contain null bytes)",
            ],
        ),
        ("ok = 1  # \u202e evil", ["line 1: holds an unseen character, U+202E"]),
        ("a\nb = '\u200b'", ["line 2: holds an unseen character, U+200B"]),
        (
            "x = '\u061c\u2028\xad'",
            [
                "line 1: holds an unseen character, U+061C",
                "line 1: holds an unseen character, U+2028",
                "line 1: holds an unseen character, U+00AD",
            ],
        ),
        (
            "x = '\U000e0041\ufe0f'",
            [
                "line 1: holds an unseen character, U+E0041",
                "line 1: holds an unseen character, U+FE0F",
            ],
        ),
    ],
)
def test_each_finding_is_a_line_for_the_approver(code: str, found: list[str]) -> None:
    assert scan(code) == found


@pytest.mark.parametrize(
    "code",
    [
        "import FreeCAD\nFreeCAD.ActiveDocument.addObject('Part::Box', 'Box')",
        "import bpy\nbpy.ops.mesh.primitive_cube_add(size=2)",
        "getattr(obj, 'Label')\nwhile n < 3:\n    n += 1\nfrom math import pi",
    ],
)
def test_the_apps_own_work_finds_nothing(code: str) -> None:
    assert scan(code) == []


def test_it_is_advisory_the_apps_own_modules_reach_past_it() -> None:
    # FreeCAD's own module runs a shell command, and the scan can't know it: the approval is
    # the gate (ADR-0085).
    assert scan("import FreeCADGui\nFreeCADGui.doCommand('import os; os.system(\"ls\")')") == []


def test_the_vetted_entries_offer_no_code_by_default_and_never_a_host_tool() -> None:
    for server in (FREECAD, BLENDER):
        assert set(server.code) == {n for n, tool in server.tools.items() if tool.risk == "code"}
        assert server.key == f"connect:{server.app}"
        assert server.code_key == f"connect-code:{server.app}"
    assert FREECAD.tools["execute_code_headless"].risk == "host"
    assert BLENDER.tools["import_asset"].risk == "network"
    assert (FREECAD.token, BLENDER.token) == ("FREECAD_MCP_TOKEN", None)
    assert BLENDER.env == {"DISABLE_TELEMETRY": "true"}
