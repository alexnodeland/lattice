"""stackr's scripts/check-template: `check_bun`, which keeps the image's Bun lattice's own."""

import importlib.machinery
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / "packages" / "stackr" / "scripts" / "check-template"
DIGEST = "sha256:" + "0" * 64


def load() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("check_template", str(SCRIPT))
    spec = importlib.util.spec_from_loader("check_template", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


check_template = load()


def lattice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bun: str) -> None:
    """A lattice whose .prototools pins this Bun."""
    root = tmp_path / "lattice"
    root.mkdir()
    (root / ".prototools").write_text(f'node = "24"\nbun = "{bun}"\n')
    monkeypatch.setattr(check_template, "LATTICE", root)


def app(tmp_path: Path, stage: str) -> Path:
    path = tmp_path / "app"
    path.mkdir()
    (path / "Dockerfile").write_text(f"FROM python:3.14 AS build\n{stage}\nRUN true\n")
    return path


def test_the_bun_the_image_builds_with_is_the_one_lattice_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lattice(tmp_path, monkeypatch, "1.4.3")
    built = app(tmp_path, f"FROM oven/bun:1.4.3@{DIGEST} AS portal-ui")
    assert check_template.check_bun(built) == []


def test_another_bun_is_a_problem_that_names_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lattice(tmp_path, monkeypatch, "1.4.4")
    built = app(tmp_path, f"FROM oven/bun:1.4.3@{DIGEST} AS portal-ui")
    [problem] = check_template.check_bun(built)
    assert "Bun is 1.4.3" in problem
    assert "says 1.4.4" in problem


def test_a_lattice_that_pins_no_bun_is_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lattice(tmp_path, monkeypatch, "1.4.3")
    (check_template.LATTICE / ".prototools").write_text('node = "24"\n')
    built = app(tmp_path, f"FROM oven/bun:1.4.3@{DIGEST} AS portal-ui")
    [problem] = check_template.check_bun(built)
    assert "says None" in problem


@pytest.mark.parametrize(
    "stage",
    [
        "FROM oven/bun:1.4.3 AS portal-ui",
        "FROM oven/bun:1.4.3@sha256:abc AS portal-ui",
        "FROM python:3.14 AS portal-ui",
    ],
)
def test_a_stage_that_is_not_pinned_by_digest_is_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    lattice(tmp_path, monkeypatch, "1.4.3")
    [problem] = check_template.check_bun(app(tmp_path, stage))
    assert "isn't FROM oven/bun" in problem
