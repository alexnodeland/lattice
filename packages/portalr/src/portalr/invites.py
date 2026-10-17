"""Inviting a user: Supabase Auth creates them, or finds them, and answers with their ``sub``.

The secret key stays in the application. portalr's router then adds the user to the tenant in
grantr, which checks ``grantr:add_member`` again.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Final

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

REGISTERED: Final = frozenset({"email_exists", "user_already_exists"})
"""Supabase Auth's error codes for an email that has an account already."""


class InviteFailed(Exception):
    """Supabase Auth didn't invite or find the user."""


Invite = Callable[[str], Awaitable[str]]
"""Invites a person by email, and returns their user id, the ``sub`` of their tokens; raises
:class:`InviteFailed` if the auth service doesn't invite or find them."""


class _User(BaseModel):
    id: str


class _Error(BaseModel):
    error_code: str | None = None


_USER: Final = TypeAdapter(_User)
_ERROR: Final = TypeAdapter(_Error)


def _error_code(response: httpx.Response) -> str | None:
    try:
        return _ERROR.validate_json(response.content).error_code
    except ValidationError:
        return None


@dataclass(frozen=True)
class SupabaseInvite:
    """Supabase Auth's admin API.

    A new person gets Supabase's invitation email. A person who has an account is found, and
    gets no email: the membership is what changes for them.

    Args:
        url: The Supabase project's URL.
        secret_key: The project's secret (service role) key.
        client: The HTTP client to send requests with.
    """

    url: str
    secret_key: str = field(repr=False)
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def __call__(self, email: str) -> str:
        """Invite a new person, or find one with an account, and return their user id.

        Raises:
            InviteFailed: If Supabase didn't answer, refused, or answered without a user.
        """
        headers = {"apikey": self.secret_key, "Authorization": f"Bearer {self.secret_key}"}
        invited = await self._post("/auth/v1/invite", {"email": email}, headers)
        if invited.status_code == 422 and _error_code(invited) in REGISTERED:
            # Already registered: a magic link, generated and not sent, names the user. The link
            # itself is discarded here, and never logged.
            invited = await self._post(
                "/auth/v1/admin/generate_link", {"type": "magiclink", "email": email}, headers
            )
        if invited.status_code >= 400:
            raise InviteFailed(f"supabase answered {invited.status_code}")
        try:
            return _USER.validate_json(invited.content).id
        except ValidationError as error:
            raise InviteFailed("supabase answered without a user") from error

    async def _post(
        self, path: str, body: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        try:
            return await self.client.post(f"{self.url}{path}", json=body, headers=headers)
        except httpx.HTTPError as error:
            raise InviteFailed(f"supabase didn't answer: {type(error).__name__}") from error
