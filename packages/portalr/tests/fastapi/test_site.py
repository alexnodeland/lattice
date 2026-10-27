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


def test_a_native_files_editor_is_served_by_its_apps_key() -> None:
    editors = {"files:wordcraft": "https://wordcraft.example.net/"}
    site = Site(supabase_url="/", supabase_key="sb_publishable_abc", editors=editors)
    assert site.editors == editors


@pytest.mark.parametrize(
    ("key", "url", "said"),
    [
        ("markdown:math", "https://editor.example.net", "no native file's app"),
        ("files:Not An App", "https://editor.example.net", "no native file's app"),
        ("files:wordcraft", "/editor", "a host, with no user or password"),
        ("files:wordcraft", "javascript:alert(1)", "a host, with no user or password"),
        ("files:wordcraft", "http://editor.example.net", "give it https"),
        ("files:wordcraft", "https://me:secret@editor.example.net", "no user or password"),
        ("files:wordcraft", "https://", "no user or password"),
    ],
)
def test_an_editor_is_an_apps_at_a_web_address(key: str, url: str, said: str) -> None:
    with pytest.raises(ValidationError, match=said):
        Site(supabase_url="/", supabase_key="sb_publishable_abc", editors={key: url})


@pytest.mark.parametrize("url", ["https://apps.example.com/editor", "https://P.supabase.co/x"])
def test_an_editor_shares_no_origin_with_the_apps_or_supabase(url: str) -> None:
    with pytest.raises(ValidationError, match="an origin of its own"):
        Site(
            supabase_url="https://p.supabase.co",
            supabase_key="sb_publishable_abc",
            apps="https://apps.example.com",
            editors={"files:gridcraft": url},
        )


def test_an_editor_on_another_port_of_the_same_host_is_its_own_origin() -> None:
    editors = {"files:gridcraft": "https://apps.example.com:8443/"}
    site = Site(
        supabase_url="/",
        supabase_key="sb_publishable_abc",
        apps="https://apps.example.com",
        editors=editors,
    )
    assert site.editors == editors


def test_an_editor_on_loopback_may_be_http_and_an_apps_own() -> None:
    editors = {"files:wordcraft": "http://127.0.0.1:8001/", "files:gridcraft": "https://g.test/"}
    assert Site(supabase_url="/", supabase_key="sb_publishable_abc", editors=editors).editors


@pytest.mark.parametrize(
    ("apps", "kept"),
    [
        ("https://apps.example.com", "https://apps.example.com"),
        # As a browser compares it, and as `location.origin` spells it: in lower case, the default
        # port left out, so an alias is found by the origin the UI is at (portalr ADR-0084).
        ("https://Apps.Example.com/", "https://apps.example.com"),
        ("https://apps.example.com:443", "https://apps.example.com"),
        ("http://127.0.0.1:8001", "http://127.0.0.1:8001"),
        (None, None),
    ],
)
def test_mini_apps_origin_is_kept_as_an_origin(apps: str | None, kept: str | None) -> None:
    assert Site(supabase_url="/", supabase_key="sb_publishable_abc", apps=apps).apps == kept


@pytest.mark.parametrize(
    ("apps", "said"),
    [
        ("http://apps.example.com", "give it https, or http on loopback"),
        ("/apps", "a host, with no user or password"),
        ("http://10.0.0.5:8801", "an IP address that isn't loopback"),
        ("https://user@apps.example.com", "no user or password"),
        ("https://", "no user or password"),
        ("https://apps.example.com/sandbox", "no path, query or fragment"),
        ("https://apps.example.com/?x=1", "no path, query or fragment"),
    ],
)
def test_mini_apps_origin_is_one_of_its_own(apps: str, said: str) -> None:
    with pytest.raises(ValidationError, match=said):
        Site(supabase_url="/", supabase_key="sb_publishable_abc", apps=apps)
