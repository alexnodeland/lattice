"""stackr's scripts/create-portal-key: the spend-read key portalr's admin gets, not the master."""

import ast
import importlib.machinery
import importlib.util
import io
import json
import re
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "packages" / "stackr" / "scripts"
READERS = ROOT / "packages" / "portalr" / "src" / "portalr" / "readers"


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
        self.deleted: list[str] = []

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
        if path == "/key/delete":
            self.aliases -= set(body["key_aliases"])
            self.deleted += body["key_aliases"]
            return {"deleted_keys": body["key_aliases"]}
        if body["key_alias"] in self.aliases:
            raise refused(400, f"Key with alias '{body['key_alias']}' already exists.")
        self.aliases.add(body["key_alias"])
        return {"key": "sk-the-new-key"}


def test_a_new_key_is_a_view_only_admins_and_opens_four_routes_only() -> None:
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
        "allowed_routes": [
            "/team/info",
            "/team/list",
            "/team/daily/activity",
            "/tag/daily/activity",
        ],
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


def test_rotating_deletes_the_key_by_its_alias_and_makes_another() -> None:
    gateway = FakeGateway(users=("portalr",), aliases=("portal-spend-read",))
    assert script.provision(gateway, lambda _: None, rotate=True) == "sk-the-new-key"
    assert gateway.deleted == ["portal-spend-read"]


def test_rotating_with_no_key_there_just_makes_one() -> None:
    class Missing(FakeGateway):
        def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            if path == "/key/delete":
                raise refused(404, "no such key")
            return super().call(method, path, body)

    assert script.provision(Missing(users=("portalr",)), lambda _: None, rotate=True)


def test_rotating_stops_when_the_key_cannot_be_deleted() -> None:
    class Refusing(FakeGateway):
        def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            if path == "/key/delete":
                raise refused(500, "the proxy is unwell")
            return super().call(method, path, body)

    with pytest.raises(SystemExit, match=r"deleting key portal-spend-read: the proxy is unwell"):
        script.provision(Refusing(users=("portalr",)), lambda _: None, rotate=True)


def test_a_400_that_is_not_the_alias_clash_stops_it() -> None:
    class Invalid(FakeGateway):
        def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            if path == "/key/generate":
                raise refused(400, "the allowed routes are invalid")
            return super().call(method, path, body)

    with pytest.raises(SystemExit, match=r"creating key"):
        script.provision(Invalid(users=("portalr",)), lambda _: None)
    assert script.provision(FakeGateway(users=("portalr",)), lambda _: None)


def run(monkeypatch: pytest.MonkeyPatch, argv: list[str], gateway: FakeGateway) -> int:
    monkeypatch.setattr(sys, "argv", ["create-portal-key", *argv])
    monkeypatch.setattr(
        script, "settings", lambda: {"LITELLM_PORT": "4000", "LITELLM_MASTER_KEY": "m"}
    )
    monkeypatch.setattr(script, "published_host", lambda _: "127.0.0.1")
    monkeypatch.setattr(script, "Gateway", lambda *_: gateway)
    return int(script.main())


@pytest.fixture
def stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("")
    monkeypatch.setattr(script, "ROOT", tmp_path)


@pytest.mark.usefixtures("stack")
def test_quiet_prints_the_key_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(monkeypatch, ["--quiet"], FakeGateway()) == 0
    assert capsys.readouterr().out == "sk-the-new-key\n"


@pytest.mark.usefixtures("stack")
def test_quiet_with_no_key_made_exits_nonzero_and_prints_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gateway = FakeGateway(users=("portalr",), aliases=("portal-spend-read",))
    assert run(monkeypatch, ["--quiet"], gateway) == script.NO_KEY
    assert capsys.readouterr().out == ""
    assert run(monkeypatch, ["--quiet", "--rotate"], gateway) == 0


@pytest.mark.usefixtures("stack")
def test_not_quiet_prints_the_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(monkeypatch, [], FakeGateway()) == 0
    assert capsys.readouterr().out == "PORTAL_LITELLM_KEY=sk-the-new-key\n"
    gateway = FakeGateway(users=("portalr",), aliases=("portal-spend-read",))
    assert run(monkeypatch, [], gateway) == 0


def test_without_an_env_file_it_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["create-portal-key"])
    with pytest.raises(SystemExit, match=r"\.env is missing"):
        script.main()


def litellm_paths() -> set[str]:
    """The LiteLLM paths portalr's readers call: the path strings in the modules that call it."""
    paths: set[str] = set()
    for name in ("litellm.py", "usage.py"):
        for node in ast.walk(ast.parse((READERS / name).read_text())):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and re.fullmatch(r"/[a-z]+(/[a-z]+)+", node.value)
            ):
                paths.add(node.value)
    return paths


def test_the_keys_routes_are_the_paths_portalrs_readers_call() -> None:
    assert litellm_paths() == set(script.ROUTES)
