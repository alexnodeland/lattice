"""The single host's edge (RFC-0004), routed for real: the shipped Caddyfile in Caddy, in front of
two stand-in backends that say what path they were sent.

`caddy validate` proves a Caddyfile parses, not where a request goes. On the application's host
only three calls reach GoTrue, the ones supabase-js's sign-in makes, and every other spelling of
the admin API, however it is escaped or traversed, must not. These tests send the raw requests.
"""

import re
import shutil
import socket
import ssl
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

HOST = Path(__file__).parent.parent / "packages" / "stackr" / "deploy" / "host"
DOMAIN = "example.test"
APP = f"app.{DOMAIN}"
AUTH = f"auth.{DOMAIN}"
STUB = ':{port} {{\n\trespond "{name} {{http.request.uri}}"\n}}\n'

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker")


def docker(*args: str) -> str:
    done = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def request(
    port: int, host: str, target: str, method: str = "GET", *, root: str
) -> tuple[int, str]:
    """One raw HTTPS request, its target exactly as given, to the edge on `port`.

    The certificate is checked against the root of Caddy's own CA (`root`, PEM), for `host`.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=root)
    with (
        socket.create_connection(("127.0.0.1", port), timeout=10) as raw,
        context.wrap_socket(raw, server_hostname=host) as tls,
    ):
        tls.sendall(
            f"{method} {target} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n"
            "Content-Length: 0\r\n\r\n".encode()
        )
        answer = b""
        while chunk := tls.recv(65536):
            answer += chunk
    head, _, body = answer.partition(b"\r\n\r\n")
    return int(head.split(b" ", 2)[1]), body.decode(errors="replace")


class Edge:
    """The edge under test: where it listens, and the root its certificates are signed by."""

    def __init__(self, port: int, root: str) -> None:
        self.port = port
        self.root = root

    def __call__(self, host: str, target: str, method: str = "GET") -> tuple[int, str]:
        return request(self.port, host, target, method, root=self.root)


def wait_for(container: str, port: int) -> Edge:
    for _ in range(60):
        try:
            root = docker("exec", container, "cat", "/data/caddy/pki/authorities/local/root.crt")
            edge = Edge(port, root)
            if edge(APP, "/ready")[0] == 200:
                return edge
        except (OSError, ValueError, IndexError, subprocess.CalledProcessError):
            time.sleep(0.5)
    pytest.fail("the edge did not come up")


@pytest.fixture(scope="module")
def edge(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Edge]:
    """The edge, with its backends up; all removed afterwards, by label."""
    found = re.search(r"image: (caddy:\S+)", (HOST / "compose.prod.yaml").read_text())
    assert found
    image = found[1]
    run = uuid.uuid4().hex[:8]
    label = f"stackr-probe=edge-{run}"
    work = tmp_path_factory.mktemp("edge")
    network = f"stackr-edge-{run}"
    docker("network", "create", "--label", label, network)
    try:
        for name, port in (("gotrue", 9999), ("app", 8000)):
            (work / name).write_text(STUB.format(port=port, name=name))
            docker(
                *("run", "-d", "--label", label, "--network", network, "--network-alias", name),
                *("-v", f"{work / name}:/etc/caddy/Caddyfile:ro", image),
            )
        container = docker(
            *("run", "-d", "--label", label, "--network", network, "-p", "127.0.0.1::443"),
            *("-e", f"STACKR_DOMAIN={DOMAIN}", "-e", "CADDY_TLS=tls internal"),
            *("-v", f"{HOST / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", image),
        )
        port = int(docker("port", container, "443/tcp").splitlines()[0].rsplit(":", 1)[1])
        yield wait_for(container, port)
    finally:
        for found_id in docker("ps", "-aq", "--filter", f"label={label}").split():
            docker("rm", "-f", "-v", found_id)
        docker("network", "rm", network)


@pytest.mark.parametrize(
    ("method", "target", "reaches"),
    [
        ("POST", "/auth/v1/token?grant_type=password", "gotrue /token?grant_type=password"),
        (
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            "gotrue /token?grant_type=refresh_token",
        ),
        ("GET", "/auth/v1/user", "gotrue /user"),
        ("POST", "/auth/v1/logout?scope=global", "gotrue /logout?scope=global"),
    ],
)
def test_the_calls_the_sign_in_makes_reach_gotrue(
    edge: Edge, method: str, target: str, reaches: str
) -> None:
    assert edge(APP, target, method) == (200, reaches)


REFUSED = [
    "/auth/v1/admin/users",
    "/auth/v1/admin/users/",
    "/auth/v1/ADMIN/users",
    "/auth/v1/Admin/users",
    "/auth/v1/admin",
    "/auth/v1/admin/",
    "/auth/v1/admin%00/users",
    "/auth/v1/admin./users",
    "/auth/v1/admin%2fusers",
    "/auth/v1/admin%2Fusers",
    "/auth/v1/%61dmin/users",
    "/auth/v1/%2e%2e/admin/users",
    "/auth/v1/%2E%2E/admin/users",
    "/auth/v1/../admin/users",
    "/auth/v1/./admin/users",
    "/auth/v1//admin/users",
    "/auth/v1/token/../admin/users",
    "/auth/v1/token/%2e%2e/admin/users",
    "/auth/v1/token%2f..%2fadmin/users",
    "/auth/v1/user/../../admin/users",
    "/auth//v1/admin/users",
    "/auth/v1/..%2fadmin/users",
    "/auth/v1/%252e%252e/admin/users",
    "/auth/v1/;/admin/users",
    "/auth/v1/admin;x=1/users",
    "/admin",
    "/admin/users",
    "/ADMIN/users",
    "/x/admin/users",
    "/%61dmin/users",
    "/portalr/../admin/users",
    "/auth/v1/signup",
    "/auth/v1/invite",
    "/auth/v1/recover",
    "/auth/v1/otp",
    "/auth/v1/health",
    "/auth/v1/settings",
    "/auth/v1",
    "/auth/v1/",
    "/auth/v1/token/",
    "/auth/v1/tokens",
]


@pytest.mark.parametrize("target", REFUSED)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_every_other_call_under_the_prefix_and_every_admin_path_is_refused(
    edge: Edge, target: str, method: str
) -> None:
    status, body = edge(APP, target, method)
    assert "gotrue" not in body
    assert status in {400, 404}, (status, body)


@pytest.mark.parametrize(
    ("method", "target"),
    [
        ("GET", "/auth/v1/token"),
        ("PUT", "/auth/v1/token"),
        ("PUT", "/auth/v1/user"),
        ("POST", "/auth/v1/user"),
        ("DELETE", "/auth/v1/user"),
        ("GET", "/auth/v1/logout"),
        ("PATCH", "/auth/v1/logout"),
    ],
)
def test_the_three_calls_are_allowed_by_method_too(edge: Edge, method: str, target: str) -> None:
    status, body = edge(APP, target, method)
    assert (status, "gotrue" in body) == (404, False)


def test_the_application_and_its_admin_ui_are_still_served(edge: Edge) -> None:
    assert edge(APP, "/portalr/admin/") == (200, "app /portalr/admin/")
    assert edge(APP, "/portalr/app/") == (200, "app /portalr/app/")
    assert edge(APP, "/other") == (200, "app /other")


def test_the_auth_host_is_as_it_was(edge: Edge) -> None:
    assert edge(AUTH, "/token") == (200, "gotrue /token")
    assert edge(AUTH, "/admin/users")[0] == 404
