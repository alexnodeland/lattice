import httpx
import pytest

from portalr.invites import InviteFailed, SupabaseInvite
from tests.tools import Tool, fails, json


def supabase(tool: Tool) -> SupabaseInvite:
    return SupabaseInvite("https://project.supabase.co", "sb_secret_x", tool.client())


async def test_a_new_person_is_invited_and_answered_with_their_id() -> None:
    tool = Tool({"/auth/v1/invite": json({"id": "user-1", "email": "dan@acme.com"})})
    assert await supabase(tool)("dan@acme.com") == "user-1"
    request = tool.last
    assert request.headers["apikey"] == "sb_secret_x"
    assert request.headers["authorization"] == "Bearer sb_secret_x"
    assert request.content == b'{"email":"dan@acme.com"}'


async def test_a_person_with_an_account_is_found_without_an_email() -> None:
    tool = Tool(
        {
            "/auth/v1/invite": json({"error_code": "email_exists"}, status=422),
            "/auth/v1/admin/generate_link": json({"id": "user-2", "action_link": "https://x"}),
        }
    )
    assert await supabase(tool)("bob@acme.com") == "user-2"
    assert tool.last.content == b'{"type":"magiclink","email":"bob@acme.com"}'


@pytest.mark.parametrize(
    ("tool", "message"),
    [
        (Tool({"/auth/v1/invite": json({}, status=500)}), "supabase answered 500"),
        (
            Tool({"/auth/v1/invite": json({"error_code": "weak"}, status=422)}),
            "supabase answered 422",
        ),
        (
            Tool({"/auth/v1/invite": lambda _r: httpx.Response(422, text="no json")}),
            "supabase answered 422",
        ),
        (Tool({"/auth/v1/invite": json({"no": "id"})}), "supabase answered without a user"),
        (
            Tool({"/auth/v1/invite": fails(httpx.ConnectError)}),
            "supabase didn't answer: ConnectError",
        ),
    ],
)
async def test_a_failed_invitation_says_why(tool: Tool, message: str) -> None:
    with pytest.raises(InviteFailed, match=message):
        await supabase(tool)("dan@acme.com")


def test_the_secret_key_is_not_in_its_repr() -> None:
    assert "sb_secret_key" not in repr(
        SupabaseInvite(url="http://auth", secret_key="sb_secret_key")
    )
