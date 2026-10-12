import pytest

from grantr.core import GRANTR_ACTIONS, OPERATOR, Catalog, Invalid, ResourceKind, Role
from grantr.core.roles import BOOKKEEPING, LEVELS
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR

CATALOG = Catalog.of(ARTIFACTR, REFLEXR, PORTALR)


def _role(name: str, kind: ResourceKind = "workspace") -> frozenset[str]:
    actions = CATALOG.role(name, kind, {})
    assert actions is not None
    return actions


def test_grantrs_catalog_is_always_there() -> None:
    assert Catalog.of().actions == GRANTR_ACTIONS


def test_an_action_is_qualified() -> None:
    with pytest.raises(ValueError, match="<library>:<name>, not edit, x:Y"):
        Catalog.of({"edit", "x:Y", "artifactr:open"})


def test_a_viewer_reads_opens_and_gives_feedback() -> None:
    assert _role("viewer") == {
        "artifactr:open",
        "artifactr:read_artifacts",
        "artifactr:read_threads",
        "artifactr:read_events",
        "artifactr:give_feedback",
        "reflexr:open",
        "reflexr:read_rules",
        "reflexr:read_runs",
        "reflexr:give_feedback",
        "portalr:read_telemetry",
    }


def test_an_editor_adds_the_commands_it_names_that_the_catalogs_have() -> None:
    assert _role("editor") - _role("viewer") == {
        "artifactr:post_message",
        "artifactr:edit_artifact",
        "artifactr:propose_change",
        "artifactr:stop_run",
        "artifactr:record",
        "reflexr:publish",
        "reflexr:cancel_run",
    }


def test_rule_management_is_the_workspace_admins_alone() -> None:
    assert "reflexr:install_rule" in _role("admin")
    assert "reflexr:install_rule" not in _role("editor")
    assert _role("admin") & GRANTR_ACTIONS == {"grantr:grant", "grantr:revoke", "grantr:restrict"}


def test_the_tenant_roles_cover_every_catalog_but_the_operators_actions() -> None:
    assert _role("owner", "tenant") == CATALOG.actions - OPERATOR - BOOKKEEPING
    assert _role("owner", "tenant") - _role("admin", "tenant") == {"grantr:delete_tenant"}
    assert _role("member", "tenant") == frozenset()
    assert _role("operator", "deployment") == OPERATOR


def test_a_role_is_granted_only_at_its_levels() -> None:
    custom = {"triage": Role(name="triage", actions=frozenset({"reflexr:cancel_run"}))}
    assert CATALOG.role("viewer", "artifact", custom) == _role("viewer")
    assert CATALOG.role("triage", "rule", custom) == {"reflexr:cancel_run"}
    assert CATALOG.role("owner", "workspace", custom) is None
    assert CATALOG.role("triage", "tenant", custom) is None
    assert CATALOG.role("nobody", "workspace", custom) is None


def test_levels() -> None:
    assert [LEVELS[kind] for kind in ("deployment", "tenant", "workspace", "thread")] == [
        "deployment",
        "tenant",
        "workspace",
        "item",
    ]


@pytest.mark.parametrize(
    ("role", "message"),
    [
        (Role(name="editor", actions=frozenset({"artifactr:open"})), "built-in"),
        (Role(name="empty", actions=frozenset()), "holds no action"),
        (Role(name="wide", actions=frozenset({"grantr:create_tenant"})), "grantr:create_tenant"),
        (Role(name="tenantish", actions=frozenset({"grantr:add_member"})), "grantr:add_member"),
        (Role(name="odd", actions=frozenset({"artifactr:fly"})), "artifactr:fly"),
    ],
)
def test_a_custom_role_is_checked_against_the_catalogs(role: Role, message: str) -> None:
    with pytest.raises(Invalid, match=message):
        CATALOG.check(role)


def test_a_custom_role_from_the_catalogs_passes() -> None:
    CATALOG.check(Role(name="triage", actions=frozenset({"reflexr:cancel_run", "grantr:grant"})))


def test_no_persons_role_holds_the_bookkeeping() -> None:
    people: list[tuple[str, ResourceKind]] = [
        ("owner", "tenant"),
        ("admin", "workspace"),
        ("viewer", "artifact"),
    ]
    for name, kind in people:
        assert _role(name, kind) & BOOKKEEPING == frozenset()
    assert "artifactr:read_cursors" not in _role("viewer")
    assert "reflexr:checkpoint_run" not in _role("editor")
    assert "reflexr:checkpoint_run" in _role("admin")


def test_the_application_holds_the_runtime_and_every_read() -> None:
    application = _role("application", "deployment")
    assert application >= BOOKKEEPING
    assert {"artifactr:record", "reflexr:publish", "reflexr:checkpoint_run"} <= application
    assert {"artifactr:read_artifacts", "reflexr:open", "artifactr:give_feedback"} <= application
    bridge = {"artifactr:open", "artifactr:read_events", "reflexr:open", "reflexr:publish"}
    assert bridge <= application, "what relayr's bridge does, as the application"
    assert application & {"artifactr:edit_artifact", "reflexr:install_rule"} == frozenset()


def test_a_rule_publishes_checkpoints_and_reads_reflexr() -> None:
    assert _role("rule") == {
        "reflexr:open",
        "reflexr:publish",
        "reflexr:checkpoint_run",
        "reflexr:read_rules",
        "reflexr:read_runs",
    }
    assert _role("rule", "rule") == _role("rule")
    assert _role("rule") <= _role("admin"), "so a workspace's admin may grant it"
