"""The spike's small servers, standard library only: python servers.py <role>.

dns       A UDP DNS server. ``<x>.rebind.test`` alternates per name: the 1st, 3rd, ... query
          gets the public-looking upstream (198.18.94.20), the 2nd, 4th, ... gets 127.0.0.1.
          ``public.test`` and ``api.upstream.test`` always get the upstream; ``private.test``
          always 127.0.0.1. TTL 0. Every answer is logged with who asked.
authz     Envoy's HTTP ext_authz service. Resolves the request's host itself (at the dns
          server, directly), refuses RFC-0011's ranges, and on allow returns the address it
          checked as ``x-lattice-upstream``, attribution as headers Envoy lifts into dynamic
          metadata, and, for a caller that sends ``X-Lattice-Secret``, the credential.
upstream  The "internet": plain HTTP on :80 says PUBLIC; TLS on :443 echoes the headers it got.
decoy     Shares Envoy's network namespace and listens on 127.0.0.1:80: what a rebinding to
          loopback would reach. Says INTERNAL.
"""

import ipaddress
import json
import os
import random
import socket
import ssl
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "198.18.94.20"
DNS = ("198.18.94.53", 53)


def log(**fields: object) -> None:
    """One JSON line on stdout."""
    sys.stdout.write(json.dumps(fields) + "\n")
    sys.stdout.flush()


# --- dns -------------------------------------------------------------------------------------


def _qname(packet: bytes) -> tuple[str, int]:
    labels, i = [], 12
    while packet[i]:
        n = packet[i]
        labels.append(packet[i + 1 : i + 1 + n].decode())
        i += n + 1
    return ".".join(labels).lower(), i + 1


def dns() -> None:
    """Serve the spike's names on UDP 53, flipping rebind.test's answers per query."""
    counts: dict[str, int] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 53))
    log(role="dns", listening=53)
    while True:
        packet, peer = sock.recvfrom(512)
        name, end = _qname(packet)
        qtype = struct.unpack("!H", packet[end : end + 2])[0]
        question = packet[12 : end + 4]
        answer = None
        if name.endswith(".rebind.test"):
            if qtype == 1:
                counts[name] = counts.get(name, 0) + 1
                answer = UPSTREAM if counts[name] % 2 else "127.0.0.1"
            known = True
        elif name in ("public.test", "api.upstream.test"):
            answer, known = (UPSTREAM if qtype == 1 else None), True
        elif name == "private.test":
            answer, known = ("127.0.0.1" if qtype == 1 else None), True
        else:
            known = False
        flags = 0x8180 if known else 0x8183  # NOERROR or NXDOMAIN
        header = packet[:2] + struct.pack("!HHHHH", flags, 1, 1 if answer else 0, 0, 0)
        body = question
        if answer:
            body += b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 0, 4) + socket.inet_aton(answer)
        sock.sendto(header + body, peer)
        log(role="dns", client=peer[0], name=name, qtype=qtype, answer=answer, n=counts.get(name))


def resolve(name: str) -> list[str]:
    """One A query, straight to the spike's DNS server, as the authorizer's own resolver."""
    qid = random.randrange(65536)
    q = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    q += struct.pack("!HH", 1, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    sock.sendto(q, DNS)
    reply, _ = sock.recvfrom(512)
    ancount = struct.unpack("!H", reply[6:8])[0]
    _, i = _qname(reply)
    i += 4
    out = []
    for _ in range(ancount):
        i += 2  # name pointer
        rtype, _, _, rdlen = struct.unpack("!HHIH", reply[i : i + 10])
        i += 10
        if rtype == 1:
            out.append(socket.inet_ntoa(reply[i : i + rdlen]))
        i += rdlen
    return out


# --- authz -----------------------------------------------------------------------------------

REFUSED = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "fd00:ec2::254/128",
    )
]

# The stack's per-purpose caller tokens (Proxy-Authorization), and the secrets port's fake.
CALLERS = {
    "tok-sandbox-a": {"tenant": "tenant-a", "workspace": "ws-1", "purpose": "sandbox:registries"},
    "tok-litellm-a": {"tenant": "tenant-a", "workspace": "ws-1", "purpose": "litellm"},
}
SECRETS = {("tenant-a", "sec_0123456789abcdef"): "sk-INJECTED-BY-PROXY"}
STRIP = "proxy-authorization,x-lattice-secret,x-api-key,authorization"


class Authz(BaseHTTPRequestHandler):
    """Envoy's HTTP ext_authz service: every method is a check."""

    def _check(self) -> None:
        # Envoy's path_prefix names the listener; a CONNECT's check comes with no path at all.
        parts = self.path.split("/")
        listener = parts[1] if len(parts) > 1 else f"connect:{self.path}"
        authority = self.headers.get("host", "")
        host, _, port = authority.partition(":")
        token = self.headers.get("proxy-authorization", "").removeprefix("Bearer ")
        caller = CALLERS.get(token)
        if caller is None:
            self._deny(listener, host, "unknown caller")
            return
        try:
            addresses = [host] if _is_ip(host) else resolve(host)
        except OSError as e:
            self._deny(listener, host, f"resolve failed: {e}")
            return
        if not addresses:
            self._deny(listener, host, "no address")
            return
        address = addresses[0]
        if any(ipaddress.ip_address(address) in net for net in REFUSED):
            self._deny(listener, host, f"refused range: {address}", address)
            return
        credential = None
        ref = self.headers.get("x-lattice-secret")
        if ref is not None:
            credential = SECRETS.get((caller["tenant"], ref))
            if credential is None:
                self._deny(listener, host, "no such secret for this tenant", address)
                return
        upstream_port = 443 if listener == "cred" else int(port or 80)
        self.send_response(200)
        self.send_header("x-lattice-upstream", f"{address}:{upstream_port}")
        self.send_header("x-lattice-upstream-ip", address)
        self.send_header("x-lattice-tenant", caller["tenant"])
        self.send_header("x-lattice-workspace", caller["workspace"])
        self.send_header("x-lattice-purpose", caller["purpose"])
        self.send_header("x-lattice-checked", address)
        # Strip every credential header the caller sent; Authorization only if nothing replaces it.
        strip = STRIP if credential is None else STRIP.replace(",authorization", "")
        self.send_header("x-envoy-auth-headers-to-remove", strip)
        if credential is not None:
            self.send_header("authorization", f"Bearer {credential}")
        self.send_header("content-length", "0")
        self.end_headers()
        log(
            role="authz",
            listener=listener,
            host=host,
            verdict="allow",
            checked=address,
            purpose=caller["purpose"],
            injected=credential is not None,
        )

    def _deny(self, listener: str, host: str, reason: str, address: str | None = None) -> None:
        body = f"egress refused: {reason}\n".encode()
        self.send_response(403)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        log(
            role="authz",
            listener=listener,
            host=host,
            verdict="deny",
            reason=reason,
            checked=address,
        )

    def do_GET(self) -> None:
        """Check a GET."""
        self._check()

    def do_POST(self) -> None:
        """Check a POST."""
        self._check()

    def do_HEAD(self) -> None:
        """Check a HEAD."""
        self._check()

    def do_CONNECT(self) -> None:
        """Check a CONNECT (Envoy's HTTP service fails these before they arrive)."""
        self._check()

    def log_message(self, *args: object) -> None:
        """Keep the default request log quiet."""


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


# --- upstream and decoy ----------------------------------------------------------------------


def _text(word: str) -> type[BaseHTTPRequestHandler]:
    class Text(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = f"{word} (served by {self.server.server_address[0]})\n".encode()
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            log(role=word.lower(), path=self.path, peer=self.client_address[0])

        def log_message(self, *args: object) -> None:
            """Keep the default request log quiet."""

    return Text


class Echo(BaseHTTPRequestHandler):
    """The TLS upstream: answers with the SNI and the headers it received."""

    def do_GET(self) -> None:
        """Echo the request's headers."""
        got = {k.lower(): v for k, v in self.headers.items()}
        body = (
            json.dumps(
                {"tls": True, "sni": getattr(self.connection, "sni", None), "headers": got},
                indent=1,
            )
            + "\n"
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        log(role="echo", headers=got)

    def log_message(self, *args: object) -> None:
        """Keep the default request log quiet."""


def upstream() -> None:
    """Serve PUBLIC on :80 and the TLS echo on :443."""
    plain = ThreadingHTTPServer(("0.0.0.0", 80), _text("PUBLIC"))
    threading.Thread(target=plain.serve_forever, daemon=True).start()
    tls = ThreadingHTTPServer(("0.0.0.0", 443), Echo)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain("/certs/upstream.crt", "/certs/upstream.key")
    ctx.sni_callback = lambda sock, name, _ctx: setattr(sock, "sni", name)
    tls.socket = ctx.wrap_socket(tls.socket, server_side=True)
    log(role="upstream", listening=[80, 443])
    tls.serve_forever()


def main() -> None:
    """Run the role named on the command line."""
    role = sys.argv[1]
    if role == "dns":
        dns()
    elif role == "authz":
        log(role="authz", listening=9000)
        ThreadingHTTPServer(("0.0.0.0", 9000), Authz).serve_forever()
    elif role == "upstream":
        upstream()
    elif role == "decoy":
        log(role="decoy", listening="127.0.0.1:80")
        ThreadingHTTPServer(("127.0.0.1", 80), _text("INTERNAL")).serve_forever()
    else:
        raise SystemExit(f"unknown role {role}; pid {os.getpid()}")


if __name__ == "__main__":
    main()
