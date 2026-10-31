"""The authorizer over gRPC (envoy.service.auth.v3.Authorization/Check), for CONNECT.

No generated stubs: the few fields used are read and written in protobuf's wire format by
hand. Same policy as servers.py's HTTP authorizer: resolve, refuse the ranges, answer the
checked address as x-lattice-upstream.
"""

import ipaddress
import json
import sys
import time
from concurrent import futures

import grpc
from servers import CALLERS, REFUSED, resolve  # servers.py beside it; compose sets PYTHONPATH


def emit(line: str, *, flush: bool = True) -> None:
    """Write one line to stdout."""
    sys.stdout.write(line + "\n")
    if flush:
        sys.stdout.flush()


def fields(buf: bytes) -> list[tuple[int, int, bytes | int]]:
    """Decode one message's fields: (number, wire type, value)."""
    out, i = [], 0
    while i < len(buf):
        key, i = varint(buf, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            v, i = varint(buf, i)
            out.append((num, wire, v))
        elif wire == 2:
            n, i = varint(buf, i)
            out.append((num, wire, buf[i : i + n]))
            i += n
        elif wire == 1:
            i += 8
        elif wire == 5:
            i += 4
        else:
            raise ValueError(wire)
    return out


def varint(buf: bytes, i: int) -> tuple[int, int]:
    """Decode a varint at i; return it and the next index."""
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def get(buf: bytes, num: int) -> bytes:
    """The first length-delimited field numbered num, or empty."""
    return next((v for n, _, v in fields(buf) if n == num and isinstance(v, bytes)), b"")


def enc_varint(n: int) -> bytes:
    """Encode a varint."""
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def ld(num: int, payload: bytes) -> bytes:
    """Encode a length-delimited field."""
    return enc_varint(num << 3 | 2) + enc_varint(len(payload)) + payload


def vi(num: int, n: int) -> bytes:
    """Encode a varint field."""
    return enc_varint(num << 3) + enc_varint(n)


def header(key: str, value: str) -> bytes:
    """Encode a HeaderValueOption that overwrites."""
    # HeaderValueOption{header: HeaderValue{key, value}, append_action: OVERWRITE_IF_EXISTS_OR_ADD}
    return ld(1, ld(1, key.encode()) + ld(2, value.encode())) + vi(3, 2)


def struct(d: dict[str, str]) -> bytes:
    """Encode a google.protobuf.Struct of strings."""
    # google.protobuf.Struct{fields: map<string, Value{string_value}>}
    return b"".join(ld(1, ld(1, k.encode()) + ld(2, ld(3, v.encode()))) for k, v in d.items())


def check(request: bytes, _context: object) -> bytes:
    """Answer one CheckRequest with a CheckResponse."""
    http = get(get(get(request, 1), 4), 2)  # CheckRequest.attributes.request.http
    method = get(http, 2).decode()
    authority = get(http, 5).decode()
    headers = {}
    for n, _, v in fields(http):
        if n == 3 and isinstance(v, bytes):
            headers[get(v, 1).decode()] = get(v, 2).decode()
    host, _, port = authority.rpartition(":") if method == "CONNECT" else (authority, "", "80")
    caller = CALLERS.get(headers.get("proxy-authorization", "").removeprefix("Bearer "))
    address = None
    reason = None
    if caller is None:
        reason = "unknown caller"
    else:
        answers = resolve(host)
        address = answers[0] if answers else None
        if address is None:
            reason = "no address"
        elif any(ipaddress.ip_address(address) in net for net in REFUSED):
            reason = f"refused range: {address}"
    emit(
        json.dumps(
            {
                "role": "grpc-authz",
                "method": method,
                "authority": authority,
                "checked": address,
                "verdict": "deny" if reason else "allow",
                "reason": reason,
                "t": time.time(),
            }
        ),
        flush=True,
    )
    if reason is not None:
        # status{code: PERMISSION_DENIED}, denied_response{status{code: Forbidden}, body}
        return ld(1, vi(1, 7)) + ld(
            2, ld(1, vi(1, 403)) + ld(3, f"egress refused: {reason}\n".encode())
        )
    assert caller is not None
    assert address is not None
    ok = ld(2, header("x-lattice-upstream", f"{address}:{port}"))
    meta = struct(
        {
            "x-lattice-tenant": caller["tenant"],
            "x-lattice-purpose": caller["purpose"],
            "x-lattice-workspace": caller["workspace"],
            "x-lattice-checked": address,
        }
    )
    return ld(1, b"") + ld(3, ok) + ld(4, meta)


def main() -> None:
    """Serve the Authorization service on :9001."""
    handler = grpc.method_handlers_generic_handler(
        "envoy.service.auth.v3.Authorization",
        {"Check": grpc.unary_unary_rpc_method_handler(check)},
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    server.add_generic_rpc_handlers((handler,))
    server.add_insecure_port("0.0.0.0:9001")
    server.start()
    emit(json.dumps({"role": "grpc-authz", "listening": 9001}), flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
