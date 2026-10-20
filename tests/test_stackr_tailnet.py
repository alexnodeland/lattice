"""The template's scripts/tailnet.sh, against a stub of the tailscale CLI: it serves the application
on one HTTPS port for the tailnet only, never with Funnel, and changes nothing it didn't set up."""

import json
import os
import shutil
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
OURS: dict[str, Any] = {
    "TCP": {"443": {"HTTPS": True}},
    "Web": {f"{NAME}:443": {"Handlers": {"/": {"Proxy": APP}}}},
}
OTHER: dict[str, Any] = {
    "TCP": {"443": {"HTTPS": True}},
    "Web": {f"{NAME}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}}},
}
FUNNELED: dict[str, Any] = {**OURS, "AllowFunnel": {f"{NAME}:443": True}}
FUNNEL_ELSEWHERE: dict[str, Any] = {**OURS, "AllowFunnel": {f"{NAME}:8443": True}}
FORWARDED: dict[str, Any] = {"TCP": {"443": {"TCPForward": "127.0.0.1:22"}}}

# The CLI's stub: it records each call, and answers the two it is asked for JSON.
STUB = """#!/usr/bin/env bash
echo "$*" >>"$CALLS"
case "$*" in
  "serve status --json") cat "$SERVED" ;;
  "status --json") printf '{"Self": {"DNSName": "%s."}}' "$NAME" ;;
esac
"""


def run(tmp_path: Path, *arguments: str, served: dict[str, Any]) -> tuple[int, str, list[str]]:
    """The script's exit status, what it printed, and the CLI's calls."""
    stub = tmp_path / "tailscale"
    stub.write_text(STUB)
    stub.chmod(0o755)
    (tmp_path / "served.json").write_text(json.dumps(served))
    environment = {
        **os.environ,
        "TAILSCALE": str(stub),
        "UV": shutil.which("uv") or "uv",
        "CALLS": str(tmp_path / "calls"),
        "SERVED": str(tmp_path / "served.json"),
        "NAME": NAME,
    }
    done = subprocess.run(
        ["bash", str(SCRIPT), *arguments], capture_output=True, text=True, env=environment
    )
    calls = tmp_path / "calls"
    called = calls.read_text().splitlines() if calls.exists() else []
    assert not any("funnel" in call for call in called), "never Funnel"
    return done.returncode, done.stdout + done.stderr, called


@pytest.mark.parametrize(
    "served", [{}, OURS, FUNNEL_ELSEWHERE], ids=["free", "ours", "Funnel on another port"]
)
def test_on_serves_the_application_on_the_tailnet_name(
    tmp_path: Path, served: dict[str, Any]
) -> None:
    status, printed, called = run(tmp_path, "on", "443", APP, served=served)
    assert status == 0, printed
    assert f"serve --bg --yes --https=443 {APP}" in called
    assert printed == (
        f"On your tailnet only: https://{NAME}/portalr/app/ and https://{NAME}/portalr/admin/\n"
    )


def test_another_port_is_in_the_address(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "on", "8444", APP, served=OURS)
    assert status == 0, printed
    assert f"serve --bg --yes --https=8444 {APP}" in called
    assert f"https://{NAME}:8444/portalr/app/" in printed


@pytest.mark.parametrize("action", ["on", "off"])
@pytest.mark.parametrize("served", [OTHER, FORWARDED], ids=["another server", "a TCP forward"])
def test_a_port_something_else_has_is_refused_and_left_as_it_is(
    tmp_path: Path, action: str, served: dict[str, Any]
) -> None:
    status, printed, called = run(tmp_path, action, "443", APP, served=served)
    assert status == 1
    assert "choose another, such as TAILNET_PORT=8444" in printed
    assert called == ["serve status --json"]


def test_on_refuses_a_port_funnel_puts_on_the_internet(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "on", "443", APP, served=FUNNELED)
    assert status == 1
    assert "Funnel puts it on the internet" in printed
    assert called == ["serve status --json"]


@pytest.mark.parametrize("served", [OURS, FUNNELED], ids=["ours", "ours, with Funnel"])
def test_off_removes_what_on_set_up(tmp_path: Path, served: dict[str, Any]) -> None:
    status, printed, called = run(tmp_path, "off", "443", APP, served=served)
    assert status == 0, printed
    assert called == ["serve status --json", "serve --yes --https=443 off"]
    assert printed == "No longer served on port 443, on your tailnet or by Funnel\n"


def test_off_changes_nothing_where_nothing_is_served(tmp_path: Path) -> None:
    status, printed, called = run(tmp_path, "off", "443", APP, served={})
    assert status == 0, printed
    assert called == ["serve status --json"]
    assert printed == "Nothing of this application's is served on port 443\n"


def test_without_the_cli_it_says_where_to_get_it(tmp_path: Path) -> None:
    if Path("/Applications/Tailscale.app").exists():
        pytest.skip("the macOS app is installed here, and is never run by a test")
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    done = subprocess.run(
        ["bash", str(SCRIPT), "on", "443", APP], capture_output=True, text=True, env=environment
    )
    assert done.returncode == 1
    assert "set TAILSCALE to the CLI's path" in done.stderr
