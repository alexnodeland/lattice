import pytest
from pydantic import ValidationError

from grantr.core import (
    DEPLOYMENT,
    TENANT,
    Catalog,
    Grant,
    Group,
    Membership,
    Resource,
    Role,
    User,
    memberships,
)
from grantr.core.grants import held
from tests.catalogs import ARTIFACTR

CATALOG = Catalog.of(ARTIFACTR)
WS = Resource(kind="workspace", workspace="w1")
OTHER = Resource(kind="workspace", workspace="w2")
ARTIFACT = Resource(kind="artifact", workspace="w1", id="a1")
BOB = User(id="bob")


def test_only_a_grant_on_the_deployment_is_in_no_tenant() -> None:
    with pytest.raises(ValidationError, match="in a tenant"):
        Grant(tenant=None, role="viewer", on=WS, to=BOB)
    with pytest.raises(ValidationError, match="in a tenant"):
        Grant(tenant="acme", role="operator", on=DEPLOYMENT, to=BOB)


def test_a_grant_holds_on_what_is_in_its_resource_and_nowhere_else() -> None:
    viewer = Grant(tenant="acme", role="viewer", on=WS, to=BOB)
    editor = Grant(tenant="acme", role="editor", on=ARTIFACT, to=BOB)
    assert "artifactr:edit_artifact" in held([viewer, editor], ARTIFACT, CATALOG, {})
    assert "artifactr:edit_artifact" not in held([viewer, editor], WS, CATALOG, {})
    assert held([viewer], OTHER, CATALOG, {}) == frozenset()


def test_a_role_that_cant_be_where_it_was_granted_holds_nothing() -> None:
    stray = Grant(tenant="acme", role="gone", on=WS, to=Group(id="g"))
    assert held([stray], WS, CATALOG, {}) == frozenset()
    custom = {"gone": Role(name="gone", actions=frozenset({"artifactr:open"}))}
    assert held([stray], WS, CATALOG, custom) == {"artifactr:open"}


def test_memberships_are_a_users_own_tenant_grants_by_tenant() -> None:
    grants = [
        Grant(tenant="globex", role="member", on=TENANT, to=BOB),
        Grant(tenant="acme", role="owner", on=TENANT, to=BOB),
        Grant(tenant="acme", role="member", on=TENANT, to=BOB),
        Grant(tenant="acme", role="editor", on=WS, to=BOB),
        Grant(tenant="acme", role="admin", on=TENANT, to=Group(id="admins")),
        Grant(tenant=None, role="operator", on=DEPLOYMENT, to=BOB),
    ]
    assert memberships("bob", grants) == [
        Membership(tenant="acme", user="bob", roles=("member", "owner")),
        Membership(tenant="globex", user="bob", roles=("member",)),
    ]
