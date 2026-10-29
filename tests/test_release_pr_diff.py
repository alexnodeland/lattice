"""CI's check of release-please's pull requests (scripts/release_pr_diff.py, and its step in
ci.yml), in a repository of its own: only a release's version and changelog pass, and nothing
else, not even a failure to check, skips CI's jobs."""

import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import release_pr_diff as rpd
import yaml

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = '[project]\nname = "relayr-ai"\nversion = "0.1.1"\n\n[tool.x]\nversion = "1.0.0"\n'
LOCK = (
    'version = 1\n\n[[package]]\nname = "relayr-ai"\nversion = "0.1.1"\n'
    'source = { editable = "packages/relayr" }\n\n'
    '[[package]]\nname = "httpx"\nversion = "0.28.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
)
MANIFEST = '{\n  "packages/relayr": "0.1.1"\n}\n'
CHANGELOG = (
    "# Changelog\n\n"
    "## [0.1.1](https://github.com/alexnodeland/lattice/compare/a...b) (2026-10-01)\n"
)
NOTES = (
    "## [0.2.0](https://github.com/alexnodeland/lattice/compare/relayr-v0.1.1...relayr-v0.2.0)"
    " (2026-10-29)\n\n\n### ⚠ BREAKING CHANGES\n\n### Features\n\n"
    "* **relayr:** read back what people change "
    "([#380](https://github.com/alexnodeland/lattice/issues/380)) "
    "([857ccdb](https://github.com/alexnodeland/lattice/commit/857ccdb))\n\n"
)
PYPROJECT_PATH = "packages/relayr/pyproject.toml"
CHANGELOG_PATH = "packages/relayr/CHANGELOG.md"

Repo = Callable[..., Path]


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def write(root: Path, files: dict[str, str | bytes | None]) -> None:
    for path, content in files.items():
        target = root / path
        if content is None:
            target.unlink()
        elif isinstance(content, bytes):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)


def released(version: str = "0.2.0") -> dict[str, str | bytes | None]:
    return {
        PYPROJECT_PATH: PYPROJECT.replace('"0.1.1"', f'"{version}"'),
        "uv.lock": LOCK.replace('"0.1.1"', f'"{version}"'),
        ".release-please-manifest.json": MANIFEST.replace("0.1.1", version),
        CHANGELOG_PATH: CHANGELOG.replace("# Changelog\n\n", "# Changelog\n\n" + NOTES),
    }


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """A repository at a base, and a function committing a release's head on top of it."""
    write(
        tmp_path,
        {
            PYPROJECT_PATH: PYPROJECT,
            "uv.lock": LOCK,
            ".release-please-manifest.json": MANIFEST,
            CHANGELOG_PATH: CHANGELOG,
            "scripts/release_pr_diff.py": (ROOT / "scripts/release_pr_diff.py").read_text(),
        },
    )
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "release")

    def head(files: dict[str, str | bytes | None] | None = None, **changes: str | None) -> Path:
        write(tmp_path, released() | (files or {}) | changes)
        git(tmp_path, "add", "-A")
        git(tmp_path, "commit", "-qm", "release")
        return tmp_path

    return head


def problems(root: Path) -> list[str]:
    return rpd.check("main", root)


def changelog(*lines: str) -> dict[str, str | bytes | None]:
    notes = NOTES + "".join(f"{line}\n" for line in lines)
    return {CHANGELOG_PATH: CHANGELOG.replace("# Changelog\n\n", "# Changelog\n\n" + notes)}


def test_a_release_passes(repo: Repo) -> None:
    assert problems(repo()) == []


def test_another_file_fails(repo: Repo) -> None:
    assert problems(repo({"scripts/x.py": "print()\n"})) == [
        "scripts/x.py: not a file a release changes"
    ]


def test_a_workflow_fails(repo: Repo) -> None:
    assert problems(repo({".github/workflows/ci.yml": "on: push\n"})) == [
        ".github/workflows/ci.yml: not a file a release changes"
    ]


def test_a_line_but_a_version_fails(repo: Repo) -> None:
    pyproject = PYPROJECT.replace('"0.1.1"\n', '"0.2.0"\nx = 1\n')
    assert problems(repo({PYPROJECT_PATH: pyproject})) == [
        f"{PYPROJECT_PATH}: a change but one version line"
    ]


def test_a_version_under_tool_fails(repo: Repo) -> None:
    pyproject = PYPROJECT.replace('"1.0.0"', '"2.0.0"')
    assert problems(repo({PYPROJECT_PATH: pyproject})) == [
        f"{PYPROJECT_PATH}: a change but [project]'s version"
    ]


def test_content_like_a_header_fails(repo: Repo) -> None:
    pyproject = PYPROJECT.replace('"0.1.1"', '"0.2.0"') + "+++x\n--- x\n"
    assert problems(repo({PYPROJECT_PATH: pyproject})) == [
        f"{PYPROJECT_PATH}: a change but one version line"
    ]


def test_a_dependencys_version_in_uv_lock_fails(repo: Repo) -> None:
    lock = LOCK.replace('"0.1.1"', '"0.2.0"').replace('"0.28.0"', '"0.0.1"')
    assert problems(repo({"uv.lock": lock})) == [
        "uv.lock: a version not of a workspace package's: httpx"
    ]


def test_a_change_on_uv_locks_last_line_fails(repo: Repo) -> None:
    lock = LOCK.replace('"0.1.1"', '"0.2.0"') + 'version = "9.0.0"\n'
    assert problems(repo({"uv.lock": lock})) == ["uv.lock: a change but version lines"]


def test_a_lone_uv_lock_bump_fails(repo: Repo) -> None:
    assert problems(repo({PYPROJECT_PATH: PYPROJECT})) == ["no version changed in pyproject.toml"]


def test_versions_that_disagree_fail(repo: Repo) -> None:
    pyproject = PYPROJECT.replace('"0.1.1"', '"99.0.0"')
    assert problems(repo({PYPROJECT_PATH: pyproject})) == [
        "the versions don't agree: [\"('0.1.1', '0.2.0')\", \"('0.1.1', '99.0.0')\"]"
    ]


def test_a_lower_version_fails(repo: Repo) -> None:
    assert problems(repo(released("0.1.0"))) == ["not a release higher than before: 0.1.1 to 0.1.0"]


def test_a_binary_fails(repo: Repo) -> None:
    lock = LOCK.encode().replace(b"0.1.1", b"0.2\x00")
    assert problems(repo({"uv.lock": lock})) == [
        "uv.lock: M, 100644 to 100644: not a text file's change"
    ]


def test_a_new_package_fails(repo: Repo) -> None:
    assert problems(repo({"packages/new/pyproject.toml": 'version = "1.0.0"\n'})) == [
        "packages/new/pyproject.toml: A, 000000 to 100644: not a text file's change"
    ]


def test_a_deleted_file_fails(repo: Repo) -> None:
    assert problems(repo({CHANGELOG_PATH: None})) == [
        f"{CHANGELOG_PATH}: D, 100644 to 000000: not a text file's change"
    ]


def test_a_mode_change_fails(repo: Repo) -> None:
    root = repo()
    git(root, "update-index", "--chmod=+x", "uv.lock")
    git(root, "commit", "-qm", "chmod")
    assert problems(root) == ["uv.lock: M, 100644 to 100755: not a text file's change"]


def test_a_symlink_fails(repo: Repo) -> None:
    root = repo({CHANGELOG_PATH: None})
    (root / CHANGELOG_PATH).symlink_to("../../uv.lock")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "link")
    assert problems(root) == [f"{CHANGELOG_PATH}: T, 100644 to 120000: not a text file's change"]


@pytest.mark.parametrize(
    "line",
    [
        '--8<-- "/etc/passwd"',
        "* -8<- x",
        "* ---8<--- x",
        '* <iframe src="x">',
        "* x {: onclick=x }",
        "!!! note",
        "<script>x</script>",
        "a line of no shape",
        "* [x](https://example.com)",
        "* see https://evil.example",
        "* see www.evil.example",
        "* [a]: javascript:alert(1)",
        "[a]: https://evil.example",
        "* a note[^1]",
        "*[HTML]: x",
        "* run javascript:alert(1)",
        "* a \u202e reversed line",
        "* a zero\u200bwidth line",
        "* a line\u2028separated",
        "* a bell\x07",
    ],
)
def test_a_changelog_line_not_release_pleases_fails(repo: Repo, line: str) -> None:
    assert len(problems(repo(changelog(line)))) == 1


def checker_step() -> str:
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    return next(s["run"] for s in jobs["release-pr"]["steps"] if s.get("id") == "diff")


def run_step(root: Path, tmp_path: Path) -> str:
    """The step's output, `light=true` or nothing, run as Actions would, in bash with pipefail."""
    runner = tmp_path / "runner"
    runner.mkdir(exist_ok=True)
    output = runner / "output"
    output.write_text("")
    env = {
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "RUNNER_TEMP": str(runner),
        "MOON_BASE": "main",
        "GITHUB_WORKSPACE": str(root),
        "GITHUB_OUTPUT": str(output),
    }
    bash = shutil.which("bash") or "bash"
    command = [bash, "--noprofile", "--norc", "-eo", "pipefail", "-c", checker_step()]
    subprocess.run(command, cwd=root, env=env, check=True, capture_output=True)
    return output.read_text()


def test_the_step_skips_ci_on_a_release(repo: Repo, tmp_path: Path) -> None:
    assert run_step(repo(), tmp_path) == "light=true\n"


def test_the_step_runs_ci_on_anything_else(repo: Repo, tmp_path: Path) -> None:
    assert run_step(repo({"scripts/x.py": "print()\n"}), tmp_path) == ""


def test_a_module_the_pull_request_adds_is_not_imported(repo: Repo, tmp_path: Path) -> None:
    shadow = "import sys\nsys.exit(0)\n"
    root = repo({"json.py": shadow, "re.py": shadow, "subprocess.py": shadow})
    assert run_step(root, tmp_path) == ""


def test_a_base_without_the_checker_runs_ci(repo: Repo, tmp_path: Path) -> None:
    root = repo()
    git(root, "checkout", "-q", "main")
    git(root, "rm", "-q", "scripts/release_pr_diff.py")
    git(root, "commit", "-qm", "no checker")
    git(root, "checkout", "-q", "release")
    assert run_step(root, tmp_path) == ""


def test_a_scope_and_a_colon_pass(repo: Repo) -> None:
    assert problems(repo(changelog("* **relayr:** one thing: and another"))) == []


def test_unicode_digits_are_not_a_version(repo: Repo) -> None:
    assert problems(repo(released("\u0660.\u0661.\u0662"))) != []
    assert rpd.release("\u0660.\u0661.\u0662") is None


def test_a_newline_in_a_path_is_not_a_file_a_release_changes(repo: Repo) -> None:
    assert problems(repo({"a\n::error::x": "x\n"})) == [
        "a\n::error::x: not a file a release changes"
    ]


def test_the_step_stops_workflow_commands_around_the_checker() -> None:
    step = checker_step()
    assert (
        step.index("::stop-commands::$token")
        < step.index("python3 -I")
        < step.index('"::$token::"')
    )


UNGATED = {"release-pr", "dependency-review", "osv", "ci", "release-images-publish", "aws-tier2"}
"""The jobs that don't need the gate: itself, the two that run on a release too, the aggregate,
and two that need a gated job, and so skip with it."""


def test_every_other_job_is_gated_and_may_skip_only_when_light() -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    gated = set(jobs) - UNGATED
    for name in gated:
        assert jobs[name]["needs"] == "release-pr", name
        assert jobs[name]["if"] == "${{ !cancelled() && needs.release-pr.outputs.light != 'true' }}"
    assert set(jobs["ci"]["needs"]) == set(jobs) - {"ci"}
    skips = jobs["ci"]["steps"][0]["with"]["allowed-skips"]
    light = re.search(r"needs\.release-pr\.outputs\.light == 'true'\s*&& '([^']*)'", skips)
    assert light is not None
    assert {each.strip() for each in light.group(1).split(",")} == gated | {
        "release-images-publish",
        "aws-tier2",
    }
