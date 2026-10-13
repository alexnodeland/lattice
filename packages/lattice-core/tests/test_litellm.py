"""litellm_model: a pydantic-ai model over a LiteLLM proxy's model group."""

import json

import httpx2
import pytest
from pydantic_ai import Agent

from lattice_core.litellm import litellm_model, request_tags


def test_a_model_names_the_proxys_group() -> None:
    model = litellm_model("claude-sonnet", api_base="http://litellm:4000", api_key="sk-proxy")
    assert (model.model_name, model.system) == ("claude-sonnet", "litellm")
    assert str(model.client.base_url).rstrip("/") == "http://litellm:4000"


async def test_a_model_calls_the_proxy_through_its_http_client_with_its_settings() -> None:
    bodies: list[dict[str, object]] = []

    def proxy(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        reply = {"role": "assistant", "content": "Done."}
        return httpx2.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 0,
                "model": "claude-sonnet",
                "choices": [{"index": 0, "message": reply, "finish_reason": "stop"}],
            },
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(proxy))
    model = litellm_model(
        "claude-sonnet",
        api_base="http://litellm.test",
        api_key="sk-proxy",
        http_client=client,
        settings={"temperature": 0.0},
    )
    result = await Agent(model).run("Hello")
    assert result.output == "Done."
    [body] = bodies
    assert (body["model"], body["temperature"]) == ("claude-sonnet", 0.0)


@pytest.mark.parametrize(
    ("tenant", "workspace", "pair"),
    [
        ("acme", "launch", "acme/launch"),
        ("acme/eu", "q3,plan", "acme%2Feu/q3%2Cplan"),
        ("a b", "naïve~x", "a%20b/na%C3%AFve~x"),
    ],
)
def test_a_requests_tags_name_its_tenant_its_workspace_and_both(
    tenant: str, workspace: str, pair: str
) -> None:
    assert request_tags(tenant, workspace) == [
        f"tenant:{tenant}",
        f"workspace:{workspace}",
        f"tenant-workspace:{pair}",
    ]
