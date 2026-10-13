"""grantr: identity and access for artifactr and reflexr.

Tenants, their members, groups, roles and service principals, and the grants that bind them to
tenants, workspaces, threads, artifacts and rules. The libraries ask it, through their own hooks,
before every command and read; it imports neither library, and neither imports it.

The model and its rules are in :mod:`grantr.core`, with no I/O; :class:`Grants` answers checks
and changes access over a storage, such as :class:`InMemoryStorage`. The documentation, with its
decisions and the plan that builds grantr, is at <https://lattice.alexnodeland.com/grantr/>.
"""

from importlib.metadata import version

from grantr.core import (
    DEPLOYMENT,
    TENANT,
    Agent,
    AuditEntry,
    AuditEvent,
    AuditFilter,
    AuditType,
    Forbidden,
    Grant,
    Grantee,
    GrantrError,
    Group,
    Invalid,
    Member,
    Membership,
    Resource,
    ResourceKind,
    Role,
    RulePrincipal,
    ServicePrincipal,
    Subject,
    TenantId,
    User,
    UserId,
    Visibility,
    WorkspaceId,
    actor_of,
)
from grantr.grants import Access, Grants, Hooks, InMemoryStorage, Storage, SubjectOf

__version__ = version("grantr")

__all__ = [
    "DEPLOYMENT",
    "TENANT",
    "Access",
    "Agent",
    "AuditEntry",
    "AuditEvent",
    "AuditFilter",
    "AuditType",
    "Forbidden",
    "Grant",
    "Grantee",
    "GrantrError",
    "Grants",
    "Group",
    "Hooks",
    "InMemoryStorage",
    "Invalid",
    "Member",
    "Membership",
    "Resource",
    "ResourceKind",
    "Role",
    "RulePrincipal",
    "ServicePrincipal",
    "Storage",
    "Subject",
    "SubjectOf",
    "TenantId",
    "User",
    "UserId",
    "Visibility",
    "WorkspaceId",
    "__version__",
    "actor_of",
]
