"""The ids grantr shares with the libraries, and its own.

A tenant and a workspace have the same ids as in artifactr and reflexr. A user is a Supabase Auth
``sub``: grantr stores the id, and no password or profile.
"""

import re
from typing import Annotated, Final

from pydantic import StringConstraints

TENANT_ID: Final = re.compile(r"^[^~]+$")
"""A tenant id's form."""

type TenantId = Annotated[str, StringConstraints(pattern=TENANT_ID.pattern)]
"""The isolation boundary, as the libraries name it: not empty, and with no ``~``, which
grantr's storage keeps for the deployment."""

type WorkspaceId = str
"""A workspace in a tenant, as the libraries name it."""

type UserId = str
"""A person, by the identity provider's id for them."""
