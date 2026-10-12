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

PRINCIPAL_ID: Final = re.compile(r"^[^:~\s]+$")
"""A service principal's id's form."""

type PrincipalId = Annotated[str, StringConstraints(pattern=PRINCIPAL_ID.pattern)]
"""A service principal: not empty, and with no ``:``, ``~`` or whitespace. The ids the
libraries' own actors take hold a ``:``, as relayr's code rules' do (``reflexr:<rule>``), so no
principal a tenant makes, and no key it issues, can pass for one (grantr ADR-0028)."""

type WorkspaceId = str
"""A workspace in a tenant, as the libraries name it."""

type UserId = str
"""A person, by the identity provider's id for them."""
