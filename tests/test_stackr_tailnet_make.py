"""The generated Makefile's `make tailnet` guard, with scripts/tailnet.sh replaced by a stub.

`make tailnet` refuses before the script runs where the next `make up` couldn't put mini apps and
the editors beside the tailnet name: on a single host, or with them off this machine's loopback.
`make tailnet-off` is never refused, so what was served can always be removed.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUB = '#!/usr/bin/env bash\necho "$*" >>called\n'
REFUSED = "make tailnet: nothing changed"


def _render(destination: Path, *data: str) -> Path:
    answers = [arg for each in ("project_name=Tailnet", *data) for arg in ("--data", each)]
    subprocess.run(
        [
            *(sys.executable, "-m", "copier", "copy", "--quiet", "--defaults"),
            *("--vcs-ref", "HEAD", *answers, str(ROOT), str(destination)),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    script = destination / "scripts" / "tailnet.sh"
    script.write_text(STUB)
    script.chmod(0o755)
    return destination


@pytest.fixture(scope="module")
def local(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(tmp_path_factory.mktemp("local") / "app")


@pytest.fixture(scope="module")
def host(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(tmp_path_factory.mktemp("host") / "app", "hosting=host")


def _make(application: Path, target: str, env: str) -> tuple[int, str, list[str]]:
    """`make <target> FILES=gridcraft` with .env holding `env`.

    Returns its status, what it printed, and the stub's calls.
    """
    (application / ".env").write_text(env)
    called = application / "called"
    called.unlink(missing_ok=True)
    done = subprocess.run(
        ["make", "--no-print-directory", target, "FILES=gridcraft"],
        cwd=application,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = called.read_text().splitlines() if called.exists() else []
    return done.returncode, done.stdout + done.stderr, calls


pytestmark = [
    pytest.mark.timeout(300),
    pytest.mark.skipif(shutil.which("make") is None, reason="needs make"),
]


def test_a_clean_env_reaches_the_script(local: Path) -> None:
    status, printed, calls = _make(local, "tailnet", "PORTAL_APPS_URL=http://127.0.0.1:8801\n")
    assert status == 0, printed
    assert calls == ["on 443 http://127.0.0.1:8800 8801 8802"]


def test_each_linked_app_on_loopback_is_served_beside_it(local: Path) -> None:
    env = 'PORTAL_LINKS={"tracker:plane": "http://127.0.0.1:8090/", "tracker:vikunja": "http://127.0.0.1:3456"}\n'
    status, printed, calls = _make(local, "tailnet", env)
    assert status == 0, printed
    assert calls == ["on 443 http://127.0.0.1:8800 8090 3456 8802"]


@pytest.mark.parametrize(
    ("env", "why"),
    [
        ("PORTAL_APPS_URL=https://apps.example.com\n", "PORTAL_APPS_URL isn't http://127.0.0.1"),
        ('FILES_EDITORS={"files:gridcraft": "https://e.example:8802/"}\n', "FILES_EDITORS"),
        ("FILES_EDITOR_DOMAIN=example.com\n", "FILES_EDITOR_DOMAIN"),
        ('PORTAL_LINKS={"tracker:plane": "https://plane.example/"}\n', "PORTAL_LINKS"),
        ('PORTAL_LINKS={"tracker:plane": "http://localhost:8090/"}\n', "PORTAL_LINKS"),
    ],
    ids=[
        "apps off loopback",
        "FILES_EDITORS",
        "FILES_EDITOR_DOMAIN",
        "a link off loopback",
        "a link on localhost",
    ],
)
def test_make_tailnet_refuses_before_the_script(local: Path, env: str, why: str) -> None:
    status, printed, calls = _make(local, "tailnet", env)
    assert status != 0
    assert REFUSED in printed
    assert why in printed
    assert "single-host/#signing-in-to-the-portal" in printed
    assert calls == []


def test_a_single_host_refuses_make_tailnet(host: Path) -> None:
    status, printed, calls = _make(host, "tailnet", "")
    assert status != 0
    assert "on a single host" in printed
    assert calls == []


@pytest.mark.parametrize("env", ["FILES_EDITOR_DOMAIN=example.com\n", ""])
def test_tailnet_off_is_never_refused(local: Path, host: Path, env: str) -> None:
    for application in (local, host):
        status, printed, calls = _make(application, "tailnet-off", env)
        assert status == 0, printed
        assert len(calls) == 1
        assert calls[0].startswith("off 443 http://127.0.0.1:8800")
