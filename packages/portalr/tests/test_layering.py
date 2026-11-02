"""Only the readers talk to the tools, and only the router and the provider make a Tenant."""

import ast
from pathlib import Path

SOURCE = Path(__file__).parent.parent / "src" / "portalr"


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_only_the_readers_invitations_and_people_send_http() -> None:
    for path in SOURCE.rglob("*.py"):
        module = path.relative_to(SOURCE)
        if module.parts[0] != "readers" and module.name not in {"invites.py", "people.py"}:
            assert "httpx" not in _imports(path), module


def test_the_readers_know_no_web_framework() -> None:
    for path in (SOURCE / "readers").rglob("*.py"):
        assert not {
            name for name in _imports(path) if name.split(".")[0] in ("fastapi", "starlette")
        }, path


def test_only_the_router_and_the_provider_make_a_tenant() -> None:
    """Each checks grantr's action on the tenant first, as the call's subject (portalr ADR-0097)."""
    makers = {
        path.relative_to(SOURCE).as_posix()
        for path in SOURCE.rglob("*.py")
        if "portalr.tenant.allowed" in _imports(path)
    }
    assert makers == {"fastapi/router.py", "capabilities.py"}
