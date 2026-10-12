import base64
import json

import pytest
from pydantic import ValidationError

from portalr.fastapi import Site


def jwt(claims: object) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}.signature"


@pytest.mark.parametrize("key", ["sb_secret_abc", jwt({"role": "service_role"})])
def test_a_secret_key_cant_be_served(key: str) -> None:
    with pytest.raises(ValidationError, match="secret key"):
        Site(supabase_url="https://p.supabase.co", supabase_key=key)


@pytest.mark.parametrize(
    "key", ["sb_publishable_abc", jwt({"role": "anon"}), jwt(["not", "claims"]), "a.!!!.c"]
)
def test_a_publishable_key_is_served(key: str) -> None:
    assert Site(supabase_url="https://p.supabase.co", supabase_key=key).supabase_key == key
