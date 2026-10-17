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
    """A built `app`: an entry, a preloaded chunk, a lazy chunk and a stylesheet."""
    assets = root / "app" / "assets"
    assets.mkdir(parents=True)
    (assets / "index.js").write_text("export const entry = 1;\n" * 200)
    (assets / "react.js").write_text("export const react = 2;\n" * 300)
    (assets / "chat.js").write_text("export const chat = 3;\n" * 900)
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
    return root


def test_initial_is_what_index_html_loads_and_total_is_every_script_and_stylesheet(
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


def test_an_index_naming_a_file_that_is_not_built_stops_the_check(tmp_path: Path) -> None:
    static = built(
        tmp_path,
        html='<script type="module" src="/portalr/app/assets/gone.js"></script>',
    )
    with pytest.raises(SystemExit, match=r"names gone.js, which isn't built"):
        check_size.measure("app", static)


def test_a_measure_over_its_budget_or_without_one_is_a_problem() -> None:
    measured = {"initial": 100, "total": 300, "largest": 50}
    assert check_size.problems("app", measured, {"initial": 100, "total": 300, "largest": 50}) == []
    found = check_size.problems("app", measured, {"initial": 99, "total": 400})
    assert found == [
        "app's initial is 100 bytes gzipped, over its budget of 99",
        "app has no largest budget in size-budget.json",
    ]


def test_the_committed_budgets_name_both_uis_and_every_measure() -> None:
    budgets = json.loads(check_size.BUDGET.read_text())
    assert set(budgets) == set(check_size.UIS)
    for budget in budgets.values():
        assert set(budget) == set(check_size.MEASURES)


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
