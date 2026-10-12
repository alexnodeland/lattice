"""GoTrue's signing keys, and the service role's key signed with them (RFC-0004).

HCL can't make a JWK or sign a JWT, so this does, for `make env` on one machine and, on AWS, for
a one-off task. The scripts import this from their own directory, as they do `_env.py`.
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

SERVICE_ROLE_YEARS = 10
"""How long the service role's key is valid, as Supabase's own keys are."""


def _b64(number: int) -> str:
    return base64.urlsafe_b64encode(number.to_bytes(32, "big")).rstrip(b"=").decode()


def key_set() -> str:
    """A new ES256 key set, as GoTrue's `GOTRUE_JWT_KEYS` takes it: compact JSON on one line."""
    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.private_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64(numbers.public_numbers.x),
        "y": _b64(numbers.public_numbers.y),
        "d": _b64(numbers.private_value),
        "kid": str(uuid.uuid4()),
        "alg": "ES256",
        "use": "sig",
        "key_ops": ["sign", "verify"],
    }
    return json.dumps([jwk], separators=(",", ":"))


def service_role_key(keys: str) -> str:
    """The service role's key: a JWT with the `service_role` role, signed with the set's key."""
    jwk = json.loads(keys)[0]
    key = jwt.PyJWK(jwk, algorithm="ES256")
    now = int(time.time())
    claims = {"role": "service_role", "iat": now, "exp": now + SERVICE_ROLE_YEARS * 365 * 86400}
    return jwt.encode(claims, key.key, algorithm="ES256", headers={"kid": jwk["kid"]})
