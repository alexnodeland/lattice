"""The size check (scripts/check_size.py): its three measures of a built UI, and what is over."""

import gzip
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _script() -> ModuleType:
    path = Path(__file__).parent.parent / "scripts" / "check_size.py"
    spec = importlib.util.spec_from_file_location("check_size", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_size = _script()


def zipped(text: str) -> int:
    return len(gzip.compress(text.encode(), compresslevel=9, mtime=0))


def built(root: Path, *, html: str | None = None) -> Path:
    """A built `app`: an entry, a preloaded chunk, a lazy chunk and a stylesheet, and an add-on.

    The add-on `math` is a chunk of its own and katex.js; it imports react.js, which the entry does
    too. The add-on `chem` imports katex.js as well.
    """
    assets = root / "app" / "assets"
    assets.mkdir(parents=True)
    (assets / "index.js").write_text("export const entry = 1;\n" * 200)
    (assets / "react.js").write_text("export const react = 2;\n" * 300)
    (assets / "chat.js").write_text("export const chat = 3;\n" * 900)
    (assets / "math.js").write_text("export const math = 4;\n" * 700)
    (assets / "katex.js").write_text("export const katex = 5;\n" * 1100)
    (assets / "chem.js").write_text("export const chem = 6;\n" * 40)
    (assets / "index.css").write_text(".a{color:red}\n" * 100)
    (root / "app" / "scheme.js").write_text("document.dataset.scheme = 'dark';\n")
    (assets / "face.woff2").write_bytes(b"not counted" * 1000)
    (root / "app" / "index.html").write_text(
        html
        or """<script src="/portalr/app/scheme.js"></script>
<script type="module" crossorigin src="/portalr/app/assets/index.js"></script>
<link rel="modulepreload" crossorigin href="/portalr/app/assets/react.js">
<link rel="stylesheet" crossorigin href="/portalr/app/assets/index.css">
<script src="https://cdn.example/elsewhere.js"></script>"""
    )
    manifest = {
        "index.html": {
            "file": "assets/index.js",
            "isEntry": True,
            "imports": ["_react.js"],
            "dynamicImports": [
                "src/chat.tsx",
                "../ui/src/on-demand/math.ts",
                "../ui/src/on-demand/chem.ts",
            ],
            "css": ["assets/index.css"],
        },
        "_react.js": {"file": "assets/react.js"},
        "src/chat.tsx": {"file": "assets/chat.js", "isDynamicEntry": True},
        "../ui/src/on-demand/math.ts": {
            "file": "assets/math.js",
            "isDynamicEntry": True,
            "imports": ["_react.js", "_katex.js"],
        },
        "_katex.js": {"file": "assets/katex.js"},
        "../ui/src/on-demand/chem.ts": {
            "file": "assets/chem.js",
            "isDynamicEntry": True,
            "imports": ["_katex.js"],
        },
    }
    (root / "app" / ".vite").mkdir()
    (root / "app" / ".vite" / "manifest.json").write_text(json.dumps(manifest))
    return root


def test_initial_is_what_index_html_loads_and_total_every_script_and_stylesheet_but_add_ons(
    tmp_path: Path,
) -> None:
    static = built(tmp_path)
    assets = static / "app" / "assets"
    one = {name: zipped((assets / name).read_text()) for name in ("index.js", "react.js")}
    one["scheme.js"] = zipped((static / "app" / "scheme.js").read_text())
    sheet = zipped((assets / "index.css").read_text())
    chat = zipped((assets / "chat.js").read_text())
    measured = check_size.measure("app", static)
    assert measured["initial"] == sum(one.values()) + sheet
    assert measured["total"] == sum(one.values()) + sheet + chat
    assert measured["largest"] == max(*one.values(), sheet, chat)


def test_an_add_on_is_what_only_its_import_reaches_measured_apart(tmp_path: Path) -> None:
    static = built(tmp_path)
    assets = static / "app" / "assets"
    math, katex, chem = (
        zipped((assets / name).read_text()) for name in ("math.js", "katex.js", "chem.js")
    )
    # react.js, which the entry imports as well, is the UI's own; katex.js, which both add-ons
    # import, is each add-on's, since either loads it first.
    assert check_size.measure("app", static)["addons"] == {
        "math": {"total": math + katex, "largest": max(math, katex)},
        "chem": {"total": chem + katex, "largest": max(chem, katex)},
    }


def test_a_manifest_naming_a_file_that_is_not_built_stops_the_check(tmp_path: Path) -> None:
    static = built(tmp_path)
    (static / "app" / "assets" / "katex.js").unlink()
    with pytest.raises(SystemExit, match=r"manifest names katex.js, which isn't built"):
        check_size.measure("app", static)


def test_a_ui_without_a_manifest_stops_the_check_with_a_message(tmp_path: Path) -> None:
    static = built(tmp_path)
    (static / "app" / ".vite" / "manifest.json").unlink()
    with pytest.raises(SystemExit, match=r"app has no manifest: .*manifest.json is missing"):
        check_size.measure("app", static)


def test_an_index_naming_a_file_that_is_not_built_stops_the_check(tmp_path: Path) -> None:
    static = built(
        tmp_path,
        html='<script type="module" src="/portalr/app/assets/gone.js"></script>',
    )
    with pytest.raises(SystemExit, match=r"names gone.js, which isn't built"):
        check_size.measure("app", static)


def test_a_ui_that_is_not_built_stops_the_check_with_a_message(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match=r"app isn't built: .*index.html is missing"):
        check_size.measure("app", tmp_path)


def test_a_ui_without_a_budget_stops_the_check_with_a_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps({"app": {}}))
    monkeypatch.setattr(check_size, "BUDGET", budget)
    with pytest.raises(SystemExit, match=r"no budget for admin"):
        check_size.main()


def test_a_measure_over_its_budget_or_without_one_is_a_problem() -> None:
    measured = {"initial": 100, "total": 300, "largest": 50, "addons": {}}
    assert check_size.problems("app", measured, {"initial": 100, "total": 300, "largest": 50}) == []
    found = check_size.problems("app", measured, {"initial": 99, "total": 400})
    assert found == [
        "app's initial is 100 bytes gzipped, over its budget of 99",
        "app has no largest budget in size-budget.json",
    ]


def test_an_add_on_over_its_budget_without_one_or_budgeted_but_absent_is_a_problem() -> None:
    measured = {
        "initial": 1,
        "total": 1,
        "largest": 1,
        "addons": {"math": {"total": 80, "largest": 70}, "highlight": {"total": 9, "largest": 9}},
    }
    budget = {
        "initial": 1,
        "total": 1,
        "largest": 1,
        "addons": {"math": {"total": 79, "largest": 70}, "mermaid": {"total": 1, "largest": 1}},
    }
    assert check_size.problems("app", measured, budget) == [
        "app's add-on math's total is 80 bytes gzipped, over its budget of 79",
        "app's add-on highlight has no budget in size-budget.json",
        "size-budget.json has a budget for app's add-on mermaid, which app doesn't hold",
    ]


def test_the_committed_budgets_name_both_uis_and_every_measure() -> None:
    budgets = json.loads(check_size.BUDGET.read_text())
    assert set(budgets) == set(check_size.UIS)
    for budget in budgets.values():
        assert set(budget) - {"addons"} == set(check_size.MEASURES)
        for addon in budget.get("addons", {}).values():
            assert set(addon) == set(check_size.ADDON_MEASURES)


def test_main_reports_each_ui_and_fails_over_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    static = tmp_path / "static"
    for ui in check_size.UIS:
        root = static / ui
        (root / "assets").mkdir(parents=True)
        (root / "assets" / "index.js").write_text("export const entry = 1;\n" * 50)
        (root / "index.html").write_text(
            f'<script type="module" src="/portalr/{ui}/assets/index.js"></script>'
        )
        (root / ".vite").mkdir()
        (root / ".vite" / "manifest.json").write_text(
            json.dumps({"index.html": {"file": "assets/index.js", "isEntry": True}})
        )
    budget = tmp_path / "budget.json"
    monkeypatch.setattr(check_size, "STATIC", static)
    monkeypatch.setattr(check_size, "BUDGET", budget)
    roomy = {"initial": 10_000, "total": 10_000, "largest": 10_000}
    budget.write_text(json.dumps({"app": roomy, "admin": roomy}))
    assert check_size.main() == 0
    assert "check_size: app: initial" in capsys.readouterr().out
    tight = {**roomy, "total": 1}
    budget.write_text(json.dumps({"app": roomy, "admin": tight}))
    assert check_size.main() == 1
    assert "admin's total is" in capsys.readouterr().err


def test_the_report_gives_each_add_on_a_line_against_its_budget() -> None:
    measured = {
        "initial": 1_000,
        "total": 2_000,
        "largest": 900,
        "addons": {"math": {"total": 80_000, "largest": 77_000}},
    }
    budget = {"initial": 2_000, "total": 3_000, "largest": 1_000}
    assert check_size.report("app", measured, budget) == (
        "check_size: app: initial 1,000/2,000, total 2,000/3,000, largest 900/1,000\n"
        "check_size: app's add-on math: total 80,000/0, largest 77,000/0\n"
    )
