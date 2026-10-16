"""The tags that file a model request's spend under its tenant and its workspace.

LiteLLM adds up each tag's spend across every request that carries it, whichever tenant made it.
Workspace ids are each tenant's own, so ``workspace:<id>`` alone mixes tenants whose workspaces
share an id. :func:`workspace_tag` names one tenant's workspace, and :func:`parse_workspace_tag`
reads it back (lattice ADR-0019). The gateways write the tags and the portal reads them, so
this module is the format's one implementation.
"""

from typing import Final
from urllib.parse import quote, unquote

__all__ = ["WORKSPACE_TAG_PREFIX", "parse_workspace_tag", "request_tags", "workspace_tag"]

WORKSPACE_TAG_PREFIX: Final = "tenant-workspace:"
"""What every :func:`workspace_tag` starts with."""


def workspace_tag(tenant_id: str, workspace_id: str) -> str:
    """Return ``tenant-workspace:<tenant>/<workspace>``, with each id percent-encoded.

    Each id is encoded in UTF-8, every byte but those of ASCII letters, digits and ``-._~`` (RFC
    3986's unreserved characters) as ``%XX`` in uppercase hex, as ``urllib.parse.quote(id,
    safe="")`` does. So the one ``/`` in the tag is the separator, the tag holds no comma, which
    LiteLLM's tag queries split their lists on, and :func:`parse_workspace_tag` reads both ids
    back exactly. An id that isn't valid UTF-8, such as one holding a lone surrogate, raises
    :class:`UnicodeEncodeError`.
    """
    return f"{WORKSPACE_TAG_PREFIX}{quote(tenant_id, safe='')}/{quote(workspace_id, safe='')}"


def parse_workspace_tag(tag: str) -> tuple[str, str] | None:
    """Return the tenant and workspace ids a :func:`workspace_tag` names, or None for another tag.

    It strips the prefix, splits at the first ``/``, and percent-decodes each half as UTF-8. A tag
    with the prefix but no ``/``, or whose ids aren't percent-encoded UTF-8, is no workspace tag.
    """
    if not tag.startswith(WORKSPACE_TAG_PREFIX):
        return None
    tenant, separator, workspace = tag.removeprefix(WORKSPACE_TAG_PREFIX).partition("/")
    if not separator:
        return None
    try:
        return unquote(tenant, errors="strict"), unquote(workspace, errors="strict")
    except UnicodeDecodeError:
        return None


def request_tags(tenant_id: str, workspace_id: str) -> list[str]:
    """Return the tags of a model request in a tenant's workspace, in order.

    - ``tenant:<tenant id>``
    - ``workspace:<workspace id>``
    - :func:`workspace_tag`'s ``tenant-workspace:<tenant>/<workspace>``
    """
    return [
        f"tenant:{tenant_id}",
        f"workspace:{workspace_id}",
        workspace_tag(tenant_id, workspace_id),
    ]
