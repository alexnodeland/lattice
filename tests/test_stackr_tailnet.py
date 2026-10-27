"""The template's scripts/tailnet.sh, against a stub of the tailscale CLI.

It serves the portal, mini apps' origin and the running editors on their ports for the tailnet
only, never with Funnel, all or nothing, writes one key to .env, and changes nothing it didn't set
up (portalr ADR-0084).
"""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).parent.parent
    / "packages"
    / "stackr"
    / "template"
    / "{% if use_portal %}scripts{% endif %}"
    / "tailnet.sh"
)
APP = "http://127.0.0.1:8800"
NAME = "laptop.tail1234.ts.net"
ORIGIN = f"https://{NAME}"
SIBLINGS = ("8801", "8802", "8805")
"""Mini apps' port and two running editors'."""
PLAN = {"443": APP, **{port: f"http://127.0.0.1:{port}" for port in SIBLINGS}}


def served(ports: dict[str, str], *, funnel: tuple[str, ...] = ()) -> dict[str, Any]:
    """`tailscale serve status --json` with each port proxied to its target."""
    return {
        "TCP": {port: {"HTTPS": True} for port in ports},
        "Web": {f"{NAME}:{port}": {"Handlers": {"/": {"Proxy": to}}} for port, to in ports.items()},
        **({"AllowFunnel": {f"{NAME}:{port}": True for port in funnel}} if funnel else {}),
    }


OURS = served(PLAN)
COMFY = {"TCP": {"8443": {"HTTPS": True}}, "AllowFunnel": {f"{NAME}:8443": True}}
"""ComfyUI on 8443, with Funnel: never this script's."""

# The CLI's stub: it records each call, answers the two it is asked for JSON, and fails a serve
# on the port FAIL names.
STUB = """#!/usr/bin/env bash
echo "$*" >>"$CALLS"
case "$*" in
  "serve status --json") cat "$SERVED" ;;
  "status --json") printf '{"Self": {"DNSName": "%s."}}' "$NAME" ;;
  *"--https=$FAIL "*) exit 1 ;;
esac
"""
LOOK = ["status --json", "serve status --json"]
"""The two reads before anything changes."""


def run(
    tmp_path: Path,
    action: str,
    *arguments: str,
    served: dict[str, Any],
    env: str | None = "APP_PORT=8800\n",
    fail: str = "none",
) -> tuple[int, str, list[str]]:
    """The script's exit status, what it printed, and the CLI's calls, with .env holding `env`."""
    stub = tmp_path / "tailscale"
    stub.write_text(STUB)
    stub.chmod(0o755)
    (tmp_path / "served.json").write_text(json.dumps(served))
    dotenv = tmp_path / ".env"
    if env is not None and not dotenv.exists():
        dotenv.write_text(env)
        dotenv.chmod(0o600)
    environment = {
        **os.environ,
        "TAILSCALE": str(stub),
        "UV": shutil.which("uv") or "uv",
        "CALLS": str(tmp_path / "calls"),
        "SERVED": str(tmp_path / "served.json"),
        "NAME": NAME,
        "FAIL": fail,
        "DOTENV": str(dotenv),
    }
    done = subprocess.run(
        ["bash", str(SCRIPT), action, *(arguments or ("443", APP, *SIBLINGS))],
        capture_output=True,
        text=True,
        env=environment,
    )
    calls = tmp_path / "calls"
    called = calls.read_text().splitlines() if calls.exists() else []
    assert not any("funnel" in call for call in called), "never Funnel"
    assert not any("8443" in call for call in called), "never ComfyUI's port"
    return done.returncode, done.stdout + done.stderr, called


def serve(*ports: str) -> list[str]:
    return [f"serve --bg --yes --https={port} {PLAN[port]}" for port in ports]


def off(*ports: str) -> list[str]:
    return [f"serve --yes --https={port} off" for port in ports]


def dotenv(tmp_path: Path) -> str:
    return (tmp_path / ".env").read_text()


@pytest.mark.parametrize("before", [{}, COMFY], ids=["free", "Funnel on 8443"])
def test_on_serves_the_portal_and_its_siblings_and_writes_one_key(
    tmp_path: Path, before: dict[str, Any]
) -> None:
    status, printed, called = run(tmp_path, "on", served=before)
    assert status == 0, printed
    assert called == LOOK + serve("443", *SIBLINGS)
    assert printed == (
        f"On your tailnet only: {ORIGIN}/portalr/app/ and {ORIGIN}/portalr/admin/\n"
        "  with mini apps and the editors beside it, on ports 8801, 8802, 8805\n"
        f"{tmp_path / '.env'} now sets PORTAL_EXTRA_URLS={ORIGIN}: run `make up` to apply\n"
    )
    assert dotenv(tmp_path) == f"APP_PORT=8800\nPORTAL_EXTRA_URLS={ORIGIN}\n"
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600


def test_on_again_changes_nothing(tmp_path: Path) -> None:
    run(tmp_path, "on", served={})
    status, printed, called = run(tmp_path, "on", served=OURS)
    assert status == 0, printed
    assert called[-2:] == LOOK
    assert "run `make up`" not in printed
    assert dotenv(tmp_path).count("PORTAL_EXTRA_URLS=") == 1


def test_on_serves_only_the_ports_not_yet_its_own(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "on", served=served({"443": APP}))
    assert status == 0, printed
    assert called == LOOK + serve(*SIBLINGS)


def test_another_port_is_in_the_origin(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "on", "8444", APP, served={})
    assert status == 0, printed
    assert called == [*LOOK, f"serve --bg --yes --https=8444 {APP}"]
    assert f"{ORIGIN}:8444/portalr/app/" in printed
    assert f"PORTAL_EXTRA_URLS={ORIGIN}:8444\n" in dotenv(tmp_path)


@pytest.mark.parametrize("action", ["on", "off"])
@pytest.mark.parametrize(
    "before",
    [
        served({"8802": "http://127.0.0.1:3000"}),
        {"TCP": {"8805": {"TCPForward": "127.0.0.1:22"}}},
        {**served({"443": APP}), "TCP": {"443": {"HTTPS": True}, "8801": {"TCPForward": "x:1"}}},
    ],
    ids=["another server on an editor's port", "a TCP forward", "a TCP forward beside ours"],
)
def test_a_port_something_else_has_refuses_the_whole_plan(
    tmp_path: Path, action: str, before: dict[str, Any]
) -> None:
    status, printed, called = run(tmp_path, action, served=before)
    assert status == 1
    assert "nothing changed: something else is served on port" in printed
    assert called == LOOK
    assert dotenv(tmp_path) == "APP_PORT=8800\n"


def test_on_refuses_a_port_funnel_puts_on_the_internet(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "on", served=served(PLAN, funnel=("8802",)))
    assert status == 1
    assert "Funnel puts port 8802 on the internet" in printed
    assert called == LOOK


@pytest.mark.parametrize("arguments", [("8443", APP), ("443", APP, "8801", "8443")])
def test_8443_is_never_in_the_plan(tmp_path: Path, arguments: tuple[str, ...]) -> None:
    status, printed, called = run(tmp_path, "on", *arguments, served=COMFY)
    assert status == 1
    assert "port 8443 is left to what serves it there" in printed
    assert called == LOOK


def test_a_failed_serve_removes_only_what_this_run_added(tmp_path: Path) -> None:
    before = served({"8801": PLAN["8801"]})
    status, printed, called = run(tmp_path, "on", served=before, fail="8805")
    assert status == 1
    assert "those this run added are removed again" in printed
    assert called == LOOK + serve("443", "8802", "8805") + off("443", "8802")
    assert dotenv(tmp_path) == "APP_PORT=8800\n"


def test_on_needs_a_dotenv(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "on", served={}, env=None)
    assert status == 1
    assert "run make env first" in printed
    assert called == LOOK


def test_on_replaces_an_empty_key_in_place(tmp_path: Path) -> None:
    env = "A=1\nPORTAL_EXTRA_URLS=\nB=2"
    status, printed, _ = run(tmp_path, "on", served={}, env=env)
    assert status == 0, printed
    assert dotenv(tmp_path) == f"A=1\nPORTAL_EXTRA_URLS={ORIGIN}\nB=2"


def test_on_leaves_a_key_someone_else_set(tmp_path: Path) -> None:
    env = "PORTAL_EXTRA_URLS=https://elsewhere.example\n"
    status, printed, called = run(tmp_path, "on", served={}, env=env)
    assert status == 1
    assert "sets PORTAL_EXTRA_URLS to something else" in printed
    assert called == LOOK
    assert dotenv(tmp_path) == env


@pytest.mark.parametrize("funnel", [(), ("443",)], ids=["ours", "ours, with Funnel"])
def test_off_removes_what_on_set_up_and_its_key(tmp_path: Path, funnel: tuple[str, ...]) -> None:
    env = f"A=1\nPORTAL_EXTRA_URLS={ORIGIN}\nB=2\n"
    status, printed, called = run(tmp_path, "off", served=served(PLAN, funnel=funnel), env=env)
    assert status == 0, printed
    assert called == LOOK + off("443", *SIBLINGS)
    assert printed == (
        "No longer served on your tailnet or by Funnel: port 443, 8801, 8802, 8805\n"
        f"{tmp_path / '.env'} no longer sets PORTAL_EXTRA_URLS: run `make up` to apply\n"
    )
    assert dotenv(tmp_path) == "A=1\nB=2\n"
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600


def test_off_removes_only_its_own(tmp_path: Path) -> None:
    before = {**served({"443": APP, "8802": PLAN["8802"]}), "AllowFunnel": COMFY["AllowFunnel"]}
    before["TCP"]["8443"] = {"HTTPS": True}
    env = "PORTAL_EXTRA_URLS=https://elsewhere.example\n"
    status, printed, called = run(tmp_path, "off", served=before, env=env)
    assert status == 0, printed
    assert called == LOOK + off("443", "8802")
    assert dotenv(tmp_path) == env


def test_off_changes_nothing_where_nothing_is_served(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "off", served=COMFY)
    assert status == 0, printed
    assert called == LOOK
    assert printed == "Nothing of this application's is served on your tailnet\n"


def test_without_the_cli_it_says_where_to_get_it(tmp_path: Path) -> None:
    if Path("/Applications/Tailscale.app").exists():
        pytest.skip("the macOS app is installed here, and is never run by a test")
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    done = subprocess.run(
        ["bash", str(SCRIPT), "on", "443", APP], capture_output=True, text=True, env=environment
    )
    assert done.returncode == 1
    assert "set TAILSCALE to the CLI's path" in done.stderr
