"""What the tracker connector did in a workspace, for the portal.

What its runs filed, and how its follower is doing.

A read names its tenant as reflexr's routes do, through the application's `resolve_actor`, and
asks reflexr's `authorize` about the workspace, as reflexr's own reads do: what runs filed is
theirs to read who may read the runs (`reflexr:read_runs`), and how the follower is doing theirs
who may read what could not be published (`reflexr:read_dead_letters`). Nothing is read across
tenants, and nothing here asks the tracker anything: a link is made from the tenant's
credentials, and opening it is the tracker's to allow.
"""

from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Path, Request
from opentelemetry import trace

from lattice_core.commands import calls
from lattice_core.refusals import refusals
from reflexr.core import Rejection
from reflexr.fastapi import STATUS_CODES, ResolveActor, Unauthorized
from reflexr.workspace import Access, Workspaces
from relayr.ledger import WorkspaceKey
from relayr.telemetry import workspace_attributes
from relayr.trackers import (
    Filed,
    FiledItem,
    Following,
    Reading,
    Trackers,
    Writes,
    filed_in,
    following_in,
)

PathId = Annotated[str, Path(min_length=1)]

READ_FILED: Final = "reflexr:read_runs"
"""What a read of the items runs filed asks `authorize`: they are what the runs did."""

READ_FOLLOWING: Final = "reflexr:read_dead_letters"
"""What a read of how the follower is doing asks `authorize`: it holds what it couldn't publish."""


def tracker_reads_router(
    trackers: Trackers, workspaces: Workspaces, *, resolve_actor: ResolveActor
) -> APIRouter:
    """Return the router of the tracker connector's reads, for the portal.

    Args:
        trackers: The connector whose ledger, bindings and credentials are read.
        workspaces: reflexr's workspaces, whose `authorize` decides each read.
        resolve_actor: Authenticates each request, as reflexr's router takes it.
    """
    router = APIRouter(tags=["relayr"], responses=refusals(400, 401, 403, 422))

    async def opened(request: Request, workspace_id: str, action: str) -> WorkspaceKey:
        """The request's workspace, once `authorize` allows it the action.

        Raises:
            HTTPException: 401, if `resolve_actor` refuses the request; otherwise what reflexr's
                routes answer for its rejection, such as 403 where `authorize` refuses.
        """
        try:
            tenant_id, actor = await resolve_actor(request)
            workspace = await workspaces.open(tenant_id, workspace_id, actor=actor)
            await workspace.check(Access(action=action))
        except Unauthorized as refused:
            raise HTTPException(401, str(refused) or "unauthorized") from refused
        except Rejection as refused:
            raise HTTPException(STATUS_CODES.get(refused.code, 400), str(refused)) from refused
        trace.get_current_span().set_attributes(workspace_attributes(tenant_id, workspace_id))
        return WorkspaceKey(tenant_id, workspace_id)

    @router.get(
        "/relayr/v1/workspaces/{workspace_id}/tracker/items",
        summary="The items a workspace's runs filed",
        openapi_extra=calls("relayr.list_filed_items"),
    )
    async def filed(workspace_id: PathId, request: Request) -> Filed:
        """Each item the workspace's runs filed in its tracker, with its link and its chains."""
        return await filed_in(trackers, await opened(request, workspace_id, READ_FILED))

    @router.get(
        "/relayr/v1/workspaces/{workspace_id}/tracker",
        summary="How the tracker connector is doing in a workspace",
        openapi_extra=calls("relayr.tracker_status"),
    )
    async def following(workspace_id: PathId, request: Request) -> Following:
        """The workspace's binding, how far its follower read, and what it couldn't publish."""
        return await following_in(trackers, await opened(request, workspace_id, READ_FOLLOWING))

    return router


__all__ = ["Filed", "FiledItem", "Following", "Reading", "Writes", "tracker_reads_router"]
