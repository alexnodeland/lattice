"""litellm_model: a pydantic-ai model over a LiteLLM proxy's model group."""

import json

import httpx2
import pytest
from langfuse import propagate_attributes
from opentelemetry import context as otel_context
from pydantic_ai import Agent

from lattice_core.litellm import add_propagated_tags, litellm_model


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


def test_propagated_trace_tags_follow_a_requests_own_without_repeating_them() -> None:
    own = ["lib", "tenant:acme"]
    assert add_propagated_tags(own) == own, "outside a propagate_attributes block"
    with propagate_attributes(tags=["tenant:acme", "rule:page"]):
        with propagate_attributes(tags=["chain:c1", "rule:page"]):
            assert add_propagated_tags(own) == ["lib", "tenant:acme", "rule:page", "chain:c1"]
        assert add_propagated_tags(own) == ["lib", "tenant:acme", "rule:page"]
    assert add_propagated_tags(own) == own, "and after it"


@pytest.mark.parametrize("held", ["not a list", None, 7])
def test_something_other_than_a_list_of_tags_is_ignored(held: object) -> None:
    token = otel_context.attach(otel_context.set_value("langfuse.propagated.tags", held))
    try:
        assert add_propagated_tags(["lib"]) == ["lib"]
    finally:
        otel_context.detach(token)


def test_a_tag_that_is_not_text_is_dropped() -> None:
    token = otel_context.attach(otel_context.set_value("langfuse.propagated.tags", ["a", 1]))
    try:
        assert add_propagated_tags([]) == ["a"]
    finally:
        otel_context.detach(token)
