"""Service principal keys: ``grantr_sk_<id>_<secret>``, shown once.

A key is a public id and 32 random bytes, both in hex. grantr stores the id, the key's tenant
and principal, and a SHA-256 digest of the secret: 32 random bytes need no salt. A key is found
by its id and checked by comparing digests in constant time.
"""

import hashlib
import hmac
import re
import secrets
from typing import Final

from pydantic import BaseModel, ConfigDict

from grantr.core.ids import TenantId
from grantr.core.subjects import ServicePrincipal

KEY: Final = re.compile(r"grantr_sk_([0-9a-f]{16})_([0-9a-f]{64})")
"""A key's form: the prefix, an 8-byte id and a 32-byte secret, in hex."""


class Key(BaseModel):
    """What grantr stores of a key: never its secret."""

    model_config = ConfigDict(frozen=True)

    id: str
    tenant: TenantId
    principal: ServicePrincipal
    digest: str
    """The SHA-256 digest of the secret, in hex."""


def _digest(secret: str) -> str:
    return hashlib.sha256(bytes.fromhex(secret)).hexdigest()


def issue(tenant: TenantId, principal: ServicePrincipal) -> tuple[str, Key]:
    """A new key for a principal: the key to show once, and what to store of it."""
    key_id, secret = secrets.token_hex(8), secrets.token_hex(32)
    stored = Key(id=key_id, tenant=tenant, principal=principal, digest=_digest(secret))
    return f"grantr_sk_{key_id}_{secret}", stored


def key_id(key: str) -> str | None:
    """A key's public id, or None if it isn't a key."""
    match = KEY.fullmatch(key)
    return match[1] if match else None


def verify(key: str, stored: Key) -> bool:
    """Whether a key is the one stored: its id and its secret's digest match."""
    match = KEY.fullmatch(key)
    return (
        match is not None
        and match[1] == stored.id
        and hmac.compare_digest(_digest(match[2]), stored.digest)
    )
