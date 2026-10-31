"""Spike #899, throwaway: the credential proxy and the egress proxy, outside the sandbox.

Both are reverse proxies: the sandbox is on an internal network and reaches only them.

- ``git`` (port 8080) forwards git's smart-HTTP to the forge and adds the forge token.
  For ``git-receive-pack`` it reads the ref-update commands (pkt-lines before the pack)
  and refuses any update that isn't to ``refs/heads/<branch>``, and any deletion. Only one
  repository path is allowed at all.
- ``egress`` (port 8081) forwards ``/v1/*`` to LiteLLM and adds the session's key.

Configuration is from the environment: ``FORGE_URL``, ``FORGE_USER``, ``FORGE_TOKEN``,
``REPO_PATH`` (``/owner/name.git``), ``BRANCH``, ``LITELLM_URL``, ``LITELLM_KEY``.
"""

import base64
import http.client
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ZERO = "0" * 40
HOP = {"connection", "keep-alive", "transfer-encoding", "host", "authorization", "x-api-key"}


def ref_updates(body: bytes) -> list[tuple[str, str, str]]:
    """Read the (old, new, ref) commands at the start of a receive-pack request."""
    updates: list[tuple[str, str, str]] = []
    at = 0
    while at + 4 <= len(body):
        size = int(body[at : at + 4], 16)
        if size == 0:
            break
        line = body[at + 4 : at + size].split(b"\0")[0].decode().strip()
        old, new, ref = line.split(" ", 2)
        updates.append((old, new, ref))
        at += size
    return updates


def refusal(updates: list[tuple[str, str, str]], branch: str) -> str | None:
    """Say why a push is refused, or None to allow it."""
    for _old, new, ref in updates:
        if ref != f"refs/heads/{branch}":
            return f"push to {ref} refused: only refs/heads/{branch}"
        if new == ZERO:
            return f"deleting {ref} refused"
    return None


def make_handler(upstream: str, auth: str, prefix: str, check_git: bool) -> type:
    """A handler that forwards to ``upstream``, adding ``auth``."""
    target = urlsplit(upstream)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._forward()

        def do_POST(self) -> None:
            self._forward()

        def _forward(self) -> None:
            if not self.path.startswith(prefix):
                self._refuse(403, f"{self.path} is not allowed")
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else self._read_chunked()
            if check_git and self.path.endswith("/git-receive-pack"):
                why = refusal(ref_updates(body), os.environ["BRANCH"])
                sys.stderr.write(f"git: receive-pack {ref_updates(body)} -> {why or 'ok'}\n")
                if why:
                    self._refuse(403, why)
                    return
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=300)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            headers["Authorization"] = auth
            headers["Content-Length"] = str(len(body))
            connection.request(self.command, self.path, body, headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP | {"content-length"}:
                    self.send_header(key, value)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while chunk := response.read1(65536):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            connection.close()

        def _read_chunked(self) -> bytes:
            if self.headers.get("Transfer-Encoding", "").lower() != "chunked":
                return b""
            parts: list[bytes] = []
            while size := int(self.rfile.readline().split(b";")[0], 16):
                parts.append(self.rfile.read(size))
                self.rfile.readline()
            self.rfile.readline()
            return b"".join(parts)

        def _refuse(self, status: int, why: str) -> None:
            body = why.encode() + b"\n"
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    """Serve both proxies."""
    user_token = f"{os.environ['FORGE_USER']}:{os.environ['FORGE_TOKEN']}".encode()
    git = make_handler(
        os.environ["FORGE_URL"],
        "Basic " + base64.b64encode(user_token).decode(),
        os.environ["REPO_PATH"],
        check_git=True,
    )
    egress = make_handler(
        os.environ["LITELLM_URL"], "Bearer " + os.environ["LITELLM_KEY"], "/v1/", False
    )
    servers = [ThreadingHTTPServer(("0.0.0.0", 8080), git)]
    servers.append(ThreadingHTTPServer(("0.0.0.0", 8081), egress))
    threads = [threading.Thread(target=s.serve_forever) for s in servers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
