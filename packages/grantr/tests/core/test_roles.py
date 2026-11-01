import pytest

from grantr.core import GRANTR_ACTIONS, OPERATOR, Catalog, Invalid, ResourceKind, Role
from grantr.core.roles import (
    BOOKKEEPING,
    CODE_RULE_WRITES,
    DEPLOYMENT_READS,
    LEVELS,
    TENANT_ADMIN_READS,
)
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
        "reflexr:read_events",
        "reflexr:give_feedback",
    }


def test_an_editor_adds_the_commands_it_names_that_the_catalogs_have() -> None:
    assert _role("editor") - _role("viewer") == {
        "artifactr:post_message",
        "artifactr:edit_artifact",
        "artifactr:propose_change",
        "artifactr:stop_run",
        "artifactr:record",
        "artifactr:use_model",
        "reflexr:publish",
        "reflexr:cancel_run",
    }


def test_rule_management_is_the_workspace_admins_alone() -> None:
    assert "reflexr:install_rule" in _role("admin")
    assert "reflexr:install_rule" not in _role("editor")
    assert _role("admin") & GRANTR_ACTIONS == {
        "grantr:grant",
        "grantr:revoke",
        "grantr:restrict",
        "grantr:manage_integrations",
        "grantr:manage_settings",
        "grantr:answer_approval",
    }


def test_the_tenant_roles_cover_every_catalog_but_the_operators_actions() -> None:
    deployment = {"portalr:read_deployment"}
    assert _role("owner", "tenant") == CATALOG.actions - OPERATOR - BOOKKEEPING - deployment
    assert _role("owner", "tenant") - _role("admin", "tenant") == {"grantr:delete_tenant"}
    assert _role("member", "tenant") == {"artifactr:read_workspaces"}, "listing what they open"
    assert "artifactr:read_workspaces" in _role("application", "deployment")
    for workspace_role in ("viewer", "editor", "admin"):
        assert "artifactr:read_workspaces" not in _role(workspace_role), "asked of the tenant"
    assert _role("operator", "deployment") == OPERATOR | deployment


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
    for (level, name), actions in CATALOG.built_in.items():
        if name not in ("application", "operator"):
            assert actions & BOOKKEEPING == frozenset(), f"{name} ({level})"
    assert "artifactr:read_cursors" not in _role("viewer")
    assert "reflexr:checkpoint_run" not in _role("editor")
    assert "reflexr:checkpoint_run" in _role("admin")


def test_a_library_catalog_has_its_bookkeeping() -> None:
    with pytest.raises(ValueError, match="lack the bookkeeping artifactr:claim_thread"):
        Catalog.of(ARTIFACTR - {"artifactr:claim_thread"})
    assert Catalog.of({"portalr:read_telemetry"}).actions >= {"portalr:read_telemetry"}


def test_the_application_holds_the_runtime_and_every_read() -> None:
    application = _role("application", "deployment")
    assert application >= BOOKKEEPING
    assert {"artifactr:record", "reflexr:publish", "reflexr:checkpoint_run"} <= application
    assert {"artifactr:read_artifacts", "reflexr:open", "artifactr:give_feedback"} <= application
    bridge = {"artifactr:open", "artifactr:read_events", "reflexr:open", "reflexr:publish"}
    assert bridge <= application, "what relayr's bridge does, as the application"
    assert application >= CODE_RULE_WRITES & CATALOG.actions, "its code rules write via relayr"
    rules = {"reflexr:install_rule", "reflexr:update_rule", "reflexr:archive_rule"}
    assert application >= rules, "relayr installs the rules people accept"
    assert "artifactr:respond_to_proposal" not in application, "a person accepts, not the app"
    assert "artifactr:read_workspaces" in application, "it lists a tenant's workspaces"
    assert application & (TENANT_ADMIN_READS | DEPLOYMENT_READS) == frozenset()


def test_a_rule_publishes_checkpoints_reads_its_workspace_and_posts_notices() -> None:
    assert _role("rule") == {
        "reflexr:open",
        "reflexr:publish",
        "reflexr:checkpoint_run",
        "reflexr:read_events",
        "reflexr:read_runs",
        "artifactr:open",
        "artifactr:post_message",
    }
    assert CATALOG.role("rule", "rule", {}) is None, "granted on a workspace only"
    assert Catalog.of(ARTIFACTR).role("rule", "workspace", {}) == frozenset(), "reflexr's rules"
    assert _role("rule") <= _role("admin"), "so a workspace's admin may grant it"


def test_portalrs_admin_reads_are_its_tenants_owners_and_admins_and_operators() -> None:
    tenant_admins = {
        name for (_, name), actions in CATALOG.built_in.items() if actions >= TENANT_ADMIN_READS
    }
    assert tenant_admins == {"owner", "admin"}
    assert _role("admin") & TENANT_ADMIN_READS == frozenset(), "not a workspace's admin"
    holders = {
        name for (_, name), actions in CATALOG.built_in.items() if DEPLOYMENT_READS & actions
    }
    assert holders == {"operator"}


def test_the_catalog_reads_as_the_roles_a_tenants_admins_grant() -> None:
    view = CATALOG.view()
    assert [(role.name, role.kinds) for role in view.roles] == [
        ("admin", ("tenant", "workspace")),
        ("owner", ("tenant",)),
        ("editor", ("workspace", "thread", "artifact", "rule")),
        ("viewer", ("workspace", "thread", "artifact", "rule")),
    ], "in the order of where each is granted; no deployment role, member or rule"
    assert set(view.custom_actions) == CATALOG.built_in["workspace", "admin"]
    assert list(view.custom_actions) == sorted(view.custom_actions)
    assert view.custom_kinds == ("workspace", "thread", "artifact", "rule")
