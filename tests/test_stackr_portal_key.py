"""stackr's scripts/create-portal-key: the spend-read key portalr's admin gets, not the master."""

import importlib.machinery
import importlib.util
import io
import json
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).parent.parent / "packages" / "stackr" / "scripts"


def load() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    loader = importlib.machinery.SourceFileLoader(
        "create_portal_key", str(SCRIPTS / "create-portal-key")
    )
    spec = importlib.util.spec_from_loader("create_portal_key", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


script = load()


def refused(code: int, message: str) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps({"error": {"message": message}}).encode())
    return urllib.error.HTTPError("http://gateway", code, message, Message(), body)


class FakeGateway:
    """A proxy that has these users and key aliases, and records what it is asked."""

    def __init__(self, users: tuple[str, ...] = (), aliases: tuple[str, ...] = ()) -> None:
        self.users = set(users)
        self.aliases = set(aliases)
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, path, body))
        if path.startswith("/user/info"):
            if "portalr" not in self.users:
                raise refused(404, "User portalr not found")
            return {"user_id": "portalr"}
        if path == "/user/new":
            self.users.add("portalr")
            return {"user_id": "portalr"}
        assert body is not None
        if body["key_alias"] in self.aliases:
            raise refused(400, f"Key with alias '{body['key_alias']}' already exists.")
        self.aliases.add(body["key_alias"])
        return {"key": "sk-the-new-key"}


def test_a_new_key_is_a_view_only_admins_and_opens_three_routes_only() -> None:
    gateway = FakeGateway()
    said: list[str] = []
    assert script.provision(gateway, said.append) == "sk-the-new-key"
    new_user = next(body for method, path, body in gateway.calls if path == "/user/new")
    assert new_user == {
        "user_id": "portalr",
        "user_role": "proxy_admin_viewer",
        "auto_create_key": False,
    }
    generated = gateway.calls[-1][2]
    assert generated == {
        "key_alias": "portal-spend-read",
        "user_id": "portalr",
        "allowed_routes": ["/team/info", "/team/list", "/team/daily/activity"],
    }
    assert "master" not in json.dumps(gateway.calls).lower()


def test_run_again_it_keeps_the_user_and_does_not_make_another_key() -> None:
    gateway = FakeGateway(users=("portalr",), aliases=("portal-spend-read",))
    said: list[str] = []
    assert script.provision(gateway, said.append) is None
    assert not any(path == "/user/new" for _, path, _ in gateway.calls)
    assert any("exists" in line for line in said)


def test_a_user_that_exists_without_the_key_gets_the_key() -> None:
    gateway = FakeGateway(users=("portalr",))
    assert script.provision(gateway, lambda _: None) == "sk-the-new-key"


@pytest.mark.parametrize("unwell", ["/user/info", "/user/new", "/key/generate"])
def test_a_proxy_that_refuses_for_another_reason_stops_it(unwell: str) -> None:
    class Refusing(FakeGateway):
        def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            if path.startswith(unwell):
                raise refused(500, "the proxy is unwell")
            return super().call(method, path, body)

    with pytest.raises(SystemExit, match=r"the proxy is unwell"):
        script.provision(Refusing(), lambda _: None)
