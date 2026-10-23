"""stackr's scripts/check-template: `check_bun`, which keeps the image's Bun lattice's own, and
`check_diagrams`, which keeps the diagrams worker's Excalidraw and Playwright one each."""

import importlib.machinery
import importlib.util
import json
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


PLAYWRIGHT = f"FROM mcr.microsoft.com/playwright:v1.64.0-noble@{DIGEST} AS diagrams-worker"
LOCKED = (
    '    "@excalidraw/excalidraw": ["@excalidraw/excalidraw@0.18.1", "", { "dependencies": '
    '{ "@excalidraw/mermaid-to-excalidraw": "2.2.2", "nanoid": "3.3.3" } }, "sha512-x"],\n'
)


def pinned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    excalidraw: str = "0.18.1",
    mermaid: str = "2.2.2",
    driver: str = "1.64.0",
    stage: str = PLAYWRIGHT,
    argument: str = "1.64.0",
    canvas: str | None = None,
) -> None:
    """A lattice whose worker, versions.env, lock, image and portalr's UIs pin these."""
    root = tmp_path / "lattice"
    stackr = root / "packages" / "stackr"
    worker = stackr / "workers" / "diagrams"
    worker.mkdir(parents=True)
    (stackr / "template").mkdir()
    (stackr / "versions.env").write_text("# Excalidraw\nEXCALIDRAW_VERSION=0.18.1\n")
    (stackr / "template" / "Dockerfile.jinja").write_text(
        f"FROM bun AS diagrams-build\nARG PLAYWRIGHT={argument}\n{stage}\n"
    )
    dependencies = {
        "@excalidraw/excalidraw": excalidraw,
        "@excalidraw/mermaid-to-excalidraw": mermaid,
        "playwright-core": driver,
    }
    (worker / "package.json").write_text(json.dumps({"dependencies": dependencies}))
    (root / "bun.lock").write_text(LOCKED)
    for ui, version in {"app": canvas, "admin": None}.items():
        (root / "packages" / "portalr" / "web" / ui).mkdir(parents=True)
        held = {} if version is None else {"@excalidraw/excalidraw": version}
        (root / "packages" / "portalr" / "web" / ui / "package.json").write_text(
            json.dumps({"dependencies": held})
        )
    monkeypatch.setattr(check_template, "LATTICE", root)
    monkeypatch.setattr(check_template, "ROOT", stackr)
    monkeypatch.setattr(check_template, "WORKER", worker)


def test_the_diagrams_worker_pins_what_versions_env_the_lock_and_its_image_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned(tmp_path, monkeypatch, canvas="0.18.1")
    assert check_template.check_diagrams() == []


def test_this_lattices_diagrams_pins_hold() -> None:
    assert check_template.check_diagrams() == []


@pytest.mark.parametrize(
    ("pins", "said"),
    [
        ({"excalidraw": "0.18.0"}, "workers/diagrams/package.json's Excalidraw is 0.18.0"),
        ({"canvas": "0.19.0"}, "web/app/package.json's Excalidraw is 0.19.0"),
        ({"mermaid": "2.3.0"}, "mermaid-to-excalidraw is 2.3.0; Excalidraw's is 2.2.2"),
        (
            {"driver": "1.64.1"},
            "Playwright image is 1.64.0; the worker's playwright-core is 1.64.1",
        ),
        (
            {"stage": "FROM mcr.microsoft.com/playwright:v1.64.0-noble AS diagrams-worker"},
            "is None",
        ),
        ({"argument": "1.63.0"}, "ARG PLAYWRIGHT is 1.63.0"),
    ],
)
def test_a_pin_that_differs_is_a_problem_that_names_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pins: dict[str, str], said: str
) -> None:
    pinned(tmp_path, monkeypatch, **pins)
    problems = check_template.check_diagrams()
    assert [problem for problem in problems if said in problem], problems


def test_a_lock_whose_format_changed_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned(tmp_path, monkeypatch)
    (check_template.LATTICE / "bun.lock").write_text("{}\n")
    [problem] = check_template.check_diagrams()
    assert "has the lock's format changed?" in problem
