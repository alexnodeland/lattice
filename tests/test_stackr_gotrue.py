"""stackr's `check-config gotrue`: GoTrue's image follows the Supabase CLI's.

The check reads the CLI's image pins over the network. These tests give it a recorded copy of
the CLI's Dockerfile (tests/fixtures), at v2.118.0, which runs supabase/gotrue:v2.197.0, so
they need none.
"""

import http.client
import importlib.machinery
import importlib.util
import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parent.parent
STACKR = ROOT / "packages" / "stackr"
CLI_DOCKERFILE = (
    Path(__file__).parent / "fixtures" / "supabase-cli-2.118.0-Dockerfile"
).read_text()
DIGEST = "sha256:1736a63078f5922b198c4cbe50f80ab9a2d3b54fe8b7b6cfb2e9dc5dbbc12c6b"


def load() -> ModuleType:
    """scripts/check-config, which has no .py suffix, as a module."""
    path = str(STACKR / "scripts" / "check-config")
    loader = importlib.machinery.SourceFileLoader("check_config", path)
    spec = importlib.util.spec_from_loader("check_config", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


check_config = load()


def stack(tmp_path: Path, *, compose: str = "v2.197.0", aws: str = "v2.197.0") -> Path:
    """A copy of the three files the check reads, with the GoTrue tags given."""
    (tmp_path / "deploy/aws/modules/stack").mkdir(parents=True)
    (tmp_path / "versions.env").write_text("SUPABASE_CLI_VERSION=2.118.0\n")
    (tmp_path / "compose.yaml").write_text(
        f"services:\n  gotrue:\n    image: supabase/gotrue:{compose}@{DIGEST}\n"
        "  other:\n    image: postgres:17\n"
    )
    (tmp_path / "deploy/aws/modules/stack/locals.tf").write_text(
        f'locals {{\n  images = {{\n    gotrue = "supabase/gotrue:{aws}@{DIGEST}"\n  }}\n}}\n'
    )
    return tmp_path


def serve(text: str) -> Callable[[str], str]:
    """A fetch that answers with a page, whatever the URL."""
    return lambda url: text


def test_the_pins_match_the_clis(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_config.check_gotrue(stack(tmp_path), serve(CLI_DOCKERFILE)) == []
    assert "GoTrue is v2.197.0" in capsys.readouterr().out


def test_it_reads_the_clis_file_at_the_pinned_tag(tmp_path: Path) -> None:
    asked: list[str] = []

    def fetch(url: str) -> str:
        asked.append(url)
        return CLI_DOCKERFILE

    check_config.check_gotrue(stack(tmp_path), fetch)
    assert asked == [
        "https://raw.githubusercontent.com/supabase/cli/v2.118.0"
        "/apps/cli-go/pkg/config/templates/Dockerfile"
    ]


def test_gotrue_ahead_of_the_cli_says_to_bump_the_cli_first(tmp_path: Path) -> None:
    problems = check_config.check_gotrue(stack(tmp_path, compose="v2.198.0"), serve(CLI_DOCKERFILE))
    assert len(problems) == 1
    assert problems[0].startswith(
        "compose.yaml runs supabase/gotrue:v2.198.0, but the Supabase CLI"
    )
    assert "bump the CLI first" in problems[0]
    assert "runs v2.197.0" in problems[0]


def test_gotrue_behind_the_cli_says_to_set_it(tmp_path: Path) -> None:
    problems = check_config.check_gotrue(stack(tmp_path, aws="v2.196.0"), serve(CLI_DOCKERFILE))
    assert len(problems) == 1
    assert problems[0].startswith(
        "deploy/aws/modules/stack/locals.tf runs supabase/gotrue:v2.196.0"
    )
    assert "set its tag to v2.197.0" in problems[0]


def test_both_pins_off_are_both_reported(tmp_path: Path) -> None:
    problems = check_config.check_gotrue(
        stack(tmp_path, compose="v2.198.0", aws="v2.198.0"), serve(CLI_DOCKERFILE)
    )
    assert len(problems) == 2


def test_a_digest_on_the_clis_pin_does_not_make_every_comparison_fail(tmp_path: Path) -> None:
    pinned = CLI_DOCKERFILE.replace(
        "FROM supabase/gotrue:v2.197.0 AS gotrue",
        f"FROM supabase/gotrue:v2.197.0@{DIGEST} AS gotrue",
    )
    assert pinned != CLI_DOCKERFILE
    assert check_config.check_gotrue(stack(tmp_path), serve(pinned)) == []


def test_gotrue_behind_the_cli_says_to_keep_the_digest(tmp_path: Path) -> None:
    [problem] = check_config.check_gotrue(stack(tmp_path, aws="v2.196.0"), serve(CLI_DOCKERFILE))
    assert "keeping its @sha256 digest pin" in problem


def test_a_tag_that_is_not_a_version_gets_no_direction(tmp_path: Path) -> None:
    [problem] = check_config.check_gotrue(
        stack(tmp_path, compose="v2.198.0-rc1"), serve(CLI_DOCKERFILE)
    )
    assert "bump the CLI first" not in problem
    assert "behind" not in problem
    assert "make them one" in problem


def test_a_cli_version_cannot_carry_a_path_into_the_url(tmp_path: Path) -> None:
    root = stack(tmp_path)
    (root / "versions.env").write_text("SUPABASE_CLI_VERSION=2.118.0/../../x\n")
    asked: list[str] = []

    def fetch(url: str) -> str:
        asked.append(url)
        return CLI_DOCKERFILE

    problems = check_config.check_gotrue(root, fetch)
    assert problems == ["versions.env has no SUPABASE_CLI_VERSION, or one that isn't a version"]
    assert asked == []


def test_the_aws_module_is_read_on_its_gotrue_line_only(tmp_path: Path) -> None:
    root = stack(tmp_path)
    locals_tf = root / "deploy/aws/modules/stack/locals.tf"
    locals_tf.write_text(
        "# supabase/gotrue:v9.9.9 is named here in a comment\n" + locals_tf.read_text()
    )
    assert check_config.check_gotrue(root, serve(CLI_DOCKERFILE)) == []


def test_a_file_that_cannot_be_read_fails_after_one_retry(tmp_path: Path) -> None:
    attempts: list[str] = []

    def fetch(url: str) -> str:
        attempts.append(url)
        raise OSError("connection refused")

    problems = check_config.check_gotrue(stack(tmp_path), fetch)
    assert len(attempts) == 1  # fetch_text retries inside; check_gotrue asks once
    assert len(problems) == 1
    assert "can't read the Supabase CLI 2.118.0's image pins" in problems[0]
    assert "connection refused" in problems[0]


def test_fetch_text_tries_twice_and_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def refuse(request: object, timeout: float) -> object:
        calls.append("try")
        raise OSError("connection refused")

    monkeypatch.setattr(check_config.urllib.request, "urlopen", refuse)
    with pytest.raises(OSError, match="connection refused"):
        check_config.fetch_text("https://example.test/Dockerfile", pause=0)
    assert len(calls) == 2


def test_fetch_text_succeeds_on_the_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([OSError("reset"), "FROM supabase/gotrue:v2.197.0 AS gotrue\n"])

    class Response:
        def __init__(self, text: str) -> None:
            self.text = text

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            return self.text.encode()

    def urlopen(request: object, timeout: float) -> Response:
        answer = next(answers)
        if isinstance(answer, OSError):
            raise answer
        return Response(answer)

    monkeypatch.setattr(check_config.urllib.request, "urlopen", urlopen)
    assert "gotrue:v2.197.0" in check_config.fetch_text("https://example.test/x", pause=0)


@pytest.mark.parametrize(
    "failure",
    [
        http.client.IncompleteRead(b"FROM supabase/go"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
    ],
    ids=["a body cut short", "bytes that aren't text"],
)
def test_fetch_text_retries_what_is_not_an_oserror(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    calls: list[str] = []

    def broken(request: object, timeout: float) -> object:
        calls.append("try")
        raise failure

    monkeypatch.setattr(check_config.urllib.request, "urlopen", broken)
    with pytest.raises(OSError, match=re.escape("https://example.test/x")) as raised:
        check_config.fetch_text("https://example.test/x", pause=0)
    assert len(calls) == 2
    assert raised.value.__cause__ is failure


def test_a_dockerfile_without_a_gotrue_line_fails(tmp_path: Path) -> None:
    problems = check_config.check_gotrue(
        stack(tmp_path), serve("FROM library/kong:2.8.1 AS kong\n")
    )
    assert len(problems) == 1
    assert "the file may have moved" in problems[0]


def test_a_stack_that_does_not_pin_gotrue_fails(tmp_path: Path) -> None:
    root = stack(tmp_path)
    (root / "compose.yaml").write_text("services:\n  other:\n    image: postgres:17\n")
    problems = check_config.check_gotrue(root, serve(CLI_DOCKERFILE))
    assert problems == ["compose.yaml doesn't pin supabase/gotrue"]


def test_the_real_files_have_pins_the_check_can_read() -> None:
    """The repository's own compose.yaml, locals.tf and versions.env, with a CLI that agrees.

    It holds only that the check can read the real files, so it doesn't change when the CLI's
    version, and with it GoTrue's, does.
    """
    tag = re.search(r"supabase/gotrue:([^@\s]+)", (STACKR / "compose.yaml").read_text())
    assert tag is not None
    agreeing = f"FROM supabase/postgres:17 AS pg\nFROM supabase/gotrue:{tag[1]} AS gotrue\n"
    assert check_config.check_gotrue(STACKR, serve(agreeing)) == []
