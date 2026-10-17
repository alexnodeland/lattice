"""Webhook signatures, as both trackers make them: HMAC-SHA256, hex, over the bytes sent."""

import hashlib
import hmac
from collections.abc import Mapping


def signed(headers: Mapping[str, str], body: bytes, secret: bytes, header: str) -> bool:
    """Whether a header, named in any case, holds the body's signature with `secret`.

    It compares bytes in constant time, so a header of any text is only a mismatch.
    """
    found = next((value for name, value in headers.items() if name.lower() == header), "")
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(found.encode(), expected.encode())
