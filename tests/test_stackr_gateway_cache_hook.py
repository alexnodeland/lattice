"""LiteLLM's hook places the Anthropic groups' prompt-cache breakpoints (ADR-0054) where the
gateway guide says, on an agent loop's messages. It runs the LiteLLM importable here (the
libraries' client pin), so it is skipped where LiteLLM isn't installed.
"""

from pathlib import Path

import pytest
import yaml

pytest.importorskip("litellm")

from litellm.integrations.anthropic_cache_control_hook import AnthropicCacheControlHook
from litellm.types.integrations.anthropic_cache_control_hook import (
    CacheControlMessageInjectionPoint,
)
from litellm.types.llms.openai import AllMessageValues

PROVIDERS = Path(__file__).parent.parent / "packages/stackr/deploy/litellm/groups/providers.yaml"


# The points as LiteLLM types them: the groups' (asserted equal below).
POINTS = [
    CacheControlMessageInjectionPoint(location="message", role="system", index=None, control=None),
    CacheControlMessageInjectionPoint(location="message", role=None, index=-1, control=None),
]


def test_the_typed_points_are_the_groups() -> None:
    given = [{key: value for key, value in point.items() if value is not None} for point in POINTS]
    groups = yaml.safe_load(PROVIDERS.read_text())["model_list"]
    for entry in groups:
        assert given == entry["litellm_params"]["cache_control_injection_points"]


def tool_loop() -> list[AllMessageValues]:
    """An agent loop's messages as pydantic-ai's OpenAI model sends them, mid tool call."""
    return [
        {"role": "system", "content": "You are a helpful agent."},
        {"role": "user", "content": "What is the weather in Paris?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "weather", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "Sunny, 21C"},
        {"role": "user", "content": [{"type": "text", "text": "And tomorrow?"}]},
    ]


def marked(messages: list[AllMessageValues]) -> list[int]:
    """The indexes of the messages a breakpoint landed on, inserted by the importable LiteLLM's
    hook, point by point (the client's pin; the proxy's 1.103.0 places them the same way, skips a
    message the client marked, and stops at Anthropic's four)."""
    for point in POINTS:
        messages = AnthropicCacheControlHook._process_message_injection(point, messages)

    def has(message: AllMessageValues) -> bool:
        content = message.get("content")
        last: object = content[-1] if isinstance(content, list) and content else {}
        return "cache_control" in message or (isinstance(last, dict) and "cache_control" in last)

    return [index for index, message in enumerate(messages) if has(message)]


def test_the_breakpoints_land_on_the_system_prompt_and_the_last_message() -> None:
    assert marked(tool_loop()) == [0, 4]


def test_a_tool_result_last_takes_the_breakpoint() -> None:
    assert marked(tool_loop()[:4]) == [0, 3]


def test_an_assistant_tool_call_without_content_takes_none() -> None:
    """A known limit: a point on an assistant message that only calls tools is lost."""
    assert marked(tool_loop()[:3]) == [0]
