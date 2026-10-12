"""The ids grantr shares with the libraries, and its own.

A tenant and a workspace have the same ids as in artifactr and reflexr. A user is a Supabase Auth
``sub``: grantr stores the id, and no password or profile.
"""

type TenantId = str
"""The isolation boundary, as the libraries name it."""

type WorkspaceId = str
"""A workspace in a tenant, as the libraries name it."""

type UserId = str
"""A person, by the identity provider's id for them."""
