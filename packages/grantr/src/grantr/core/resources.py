"""Resources: what a grant is on, and what a check is about.

There are four levels: the deployment, a tenant, a workspace, and a thread, artifact or rule in
a workspace. A resource names no tenant; the tenant is the check's. Its fields say its level,
and its parent chain is implied by them.
"""

from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from grantr.core.ids import WorkspaceId

type ResourceKind = Literal["deployment", "tenant", "workspace", "thread", "artifact", "rule"]

type ListableKind = Literal["workspace", "thread", "artifact", "rule"]
"""The kinds grantr lists: those in a tenant that grants name."""

ITEMS: Final[frozenset[ResourceKind]] = frozenset({"thread", "artifact", "rule"})
"""The kinds that live in a workspace."""


class Resource(BaseModel):
    """A resource, by its kind, its workspace if it is in one, and its id if it is an item."""

    model_config = ConfigDict(frozen=True)

    kind: ResourceKind
    workspace: WorkspaceId | None = None
    id: str | None = None
    """The thread's, artifact's or rule's id."""

    @model_validator(mode="after")
    def _fields_match_the_kind(self) -> Self:
        expected = (self.kind not in ("deployment", "tenant"), self.kind in ITEMS)
        if (self.workspace is not None, self.id is not None) != expected:
            raise ValueError(
                f"a {self.kind} names a workspace if it is in one, and an id if an item"
            )
        return self

    @property
    def parent(self) -> "Resource | None":
        """The resource this one is in: an item's workspace, a workspace's tenant."""
        if self.kind in ITEMS:
            return Resource(kind="workspace", workspace=self.workspace)
        if self.kind == "workspace":
            return TENANT
        return None

    def chain(self) -> tuple["Resource", ...]:
        """This resource and every one it is in, innermost first.

        The deployment is in nothing, and a tenant is not in the deployment: a deployment-wide
        role puts no one inside a tenant.
        """
        chain: list[Resource] = [self]
        while (parent := chain[-1].parent) is not None:
            chain.append(parent)
        return tuple(chain)


DEPLOYMENT: Final = Resource(kind="deployment")
"""The deployment, where the operator role is granted."""

TENANT: Final = Resource(kind="tenant")
"""The check's tenant."""
