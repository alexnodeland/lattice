"""Grants, and what they hold: the rule every check follows.

A grant is a role, on a resource, to a grantee. A grant on a resource holds on everything in
it: a workspace's grants hold on its threads, artifacts and rules, and a tenant's on its
workspaces. A grant on an item adds to the workspace's.
"""

from collections.abc import Iterable, Mapping
from itertools import groupby
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from grantr.core.ids import TenantId, UserId
from grantr.core.resources import Resource
from grantr.core.roles import RESTRICT, Catalog, Role
from grantr.core.subjects import Grantee, User


class Grant(BaseModel):
    """A role, on a resource, to a grantee: in a tenant, or on the deployment."""

    model_config = ConfigDict(frozen=True)

    tenant: TenantId | None
    """The tenant it is in; ``None`` for a grant on the deployment, which is in none."""

    role: str
    on: Resource
    to: Grantee

    @model_validator(mode="after")
    def _only_the_deployment_is_in_no_tenant(self) -> Self:
        if (self.tenant is None) != (self.on.kind == "deployment"):
            raise ValueError("a grant is in a tenant, unless it is on the deployment")
        return self


class Membership(BaseModel):
    """A user's place in a tenant: the roles granted to them on it."""

    model_config = ConfigDict(frozen=True)

    tenant: TenantId
    user: UserId
    roles: tuple[str, ...]
    """Their tenant roles, by name, sorted: ``member``, and ``owner`` or ``admin`` if held."""


class Visibility(BaseModel):
    """The threads and artifacts an actor may not see in one workspace.

    It has the fields of artifactr's ``Visibility``, which grantr doesn't import.
    """

    model_config = ConfigDict(frozen=True)

    threads: frozenset[str] = frozenset()
    artifacts: frozenset[str] = frozenset()


def held(
    grants: Iterable[Grant],
    on: Resource,
    catalog: Catalog,
    custom: Mapping[str, Role],
    *,
    restricted: bool = False,
) -> frozenset[str]:
    """The actions some grants hold on a resource: those of each grant on it or around it.

    On a restricted thread or artifact, a grant around it holds only if its role may restrict:
    the workspace's admins, and the tenant's owners and admins. Grants on the item itself hold
    as ever.
    """
    chain = on.chain()
    found: set[str] = set()
    for grant in grants:
        if grant.on not in chain:
            continue
        actions = catalog.role(grant.role, grant.on.kind, custom) or frozenset[str]()
        if restricted and grant.on != on and RESTRICT not in actions:
            continue
        found |= actions
    return frozenset(found)


def memberships(user: UserId, grants: Iterable[Grant]) -> list[Membership]:
    """A user's memberships, from the grants on tenants made to them directly, by tenant."""
    tenant_roles = sorted(
        (grant.tenant, grant.role)
        for grant in grants
        if grant.tenant is not None and grant.on.kind == "tenant" and grant.to == User(id=user)
    )
    return [
        Membership(tenant=tenant, user=user, roles=tuple(role for _, role in roles))
        for tenant, roles in groupby(tenant_roles, key=lambda pair: pair[0])
    ]
