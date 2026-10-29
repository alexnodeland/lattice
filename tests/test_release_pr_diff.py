"""CI's check of release-please's pull requests (scripts/release_pr_diff.py), in a repository of
its own: only versions and changelogs pass."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import release_pr_diff as rpd

PYPROJECT = '[project]\nname = "relayr-ai"\nversion = "0.1.1"\n\n[tool.x]\nversion = "1"\n'
LOCK = (
    'version = 1\n\n[[package]]\nname = "relayr-ai"\nversion = "0.1.1"\n'
    'source = { editable = "packages/relayr" }\n\n'
    '[[package]]\nname = "httpx"\nversion = "0.28.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
)
MANIFEST = '{\n  "packages/relayr": "0.1.1"\n}\n'
CHANGELOG = "# Changelog\n\n## 0.1.1\n"

Repo = Callable[..., Path]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """A repository at a base, and a function committing a release's head on top of it."""
    files = {
        "packages/relayr/pyproject.toml": PYPROJECT,
        "uv.lock": LOCK,
        ".release-please-manifest.json": MANIFEST,
        "packages/relayr/CHANGELOG.md": CHANGELOG,
    }
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "release")

    def head(**changes: str | bytes | None) -> Path:
        release = {
            "packages/relayr/pyproject.toml": PYPROJECT.replace('"0.1.1"', '"0.2.0"'),
            "uv.lock": LOCK.replace('"0.1.1"', '"0.2.0"'),
            ".release-please-manifest.json": MANIFEST.replace("0.1.1", "0.2.0"),
            "packages/relayr/CHANGELOG.md": CHANGELOG + "\n## 0.2.0\n* a feature\n",
        }
        for path, content in (release | changes).items():
            target = tmp_path / path
            if content is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content)
        git(tmp_path, "add", "-A")
        git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "release")
        return tmp_path

    return head


def problems(root: Path) -> list[str]:
    return rpd.check("main", root)


def test_a_release_passes(repo: Repo) -> None:
    assert problems(repo()) == []


def test_another_file_fails(repo: Repo) -> None:
    assert problems(repo(**{"scripts/x.py": "print()\n"})) == [
        "scripts/x.py: not a file a release changes"
    ]


def test_a_workflow_fails(repo: Repo) -> None:
    assert problems(repo(**{".github/workflows/ci.yml": "on: push\n"})) != []


def test_a_line_but_a_version_fails(repo: Repo) -> None:
    pyproject = PYPROJECT.replace('"0.1.1"\n', '"0.2.0"\nx = 1\n')
    assert problems(repo(**{"packages/relayr/pyproject.toml": pyproject})) != []


def test_a_version_under_tool_fails(repo: Repo) -> None:
    pyproject = PYPROJECT.replace('version = "1"', 'version = "2"')
    assert problems(repo(**{"packages/relayr/pyproject.toml": pyproject})) != []


def test_a_dependencys_version_in_uv_lock_fails(repo: Repo) -> None:
    lock = LOCK.replace('"0.1.1"', '"0.2.0"').replace('"0.28.0"', '"0.0.1"')
    assert problems(repo(**{"uv.lock": lock})) != []


def test_a_change_on_uv_locks_last_line_fails(repo: Repo) -> None:
    lock = LOCK.replace('"0.1.1"', '"0.2.0"') + 'version = "9"\n'
    assert problems(repo(**{"uv.lock": lock})) != []


def test_content_like_a_header_fails(repo: Repo) -> None:
    pyproject = PYPROJECT.replace('"0.1.1"', '"0.2.0"') + "+++x\n--- x\n"
    assert problems(repo(**{"packages/relayr/pyproject.toml": pyproject})) != []


def test_a_binary_fails(repo: Repo) -> None:
    assert problems(repo(**{"uv.lock": LOCK.encode().replace(b"0.1.1", b"0.2\x00")})) != []


def test_a_new_package_fails(repo: Repo) -> None:
    assert problems(repo(**{"packages/new/pyproject.toml": 'version = "1"\n'})) != []


def test_a_deleted_file_fails(repo: Repo) -> None:
    assert problems(repo(**{"packages/relayr/CHANGELOG.md": None})) != []


def test_a_mode_change_fails(repo: Repo) -> None:
    root = repo()
    git(root, "update-index", "--chmod=+x", "uv.lock")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "chmod")
    assert problems(root) != []


def test_a_symlink_fails(repo: Repo) -> None:
    root = repo(**{"packages/relayr/CHANGELOG.md": None})
    (root / "packages/relayr/CHANGELOG.md").symlink_to("../../uv.lock")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "link")
    assert problems(root) != []


def test_the_docs_syntax_in_a_changelog_fails(repo: Repo) -> None:
    changelog = CHANGELOG + '\n--8<-- "/etc/passwd"\n'
    assert problems(repo(**{"packages/relayr/CHANGELOG.md": changelog})) != []
