"""stackr's gateway puts prompt-cache breakpoints on the Anthropic groups alone (ADR-0054).

`check-config litellm` holds the groups to it; these tests run it on the real files, and on a copy
with the breakpoints taken off an Anthropic group or put on another.
"""

import importlib.machinery
import importlib.util
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from litellm.integrations.anthropic_cache_control_hook import AnthropicCacheControlHook
from litellm.types.integrations.anthropic_cache_control_hook import (
    CacheControlMessageInjectionPoint,
)
from litellm.types.llms.openai import AllMessageValues

STACKR = Path(__file__).parent.parent / "packages" / "stackr"
GROUPS = STACKR / "deploy" / "litellm" / "groups"


def load() -> ModuleType:
    """scripts/check-config, which has no .py suffix, as a module."""
    path = str(STACKR / "scripts" / "check-config")
    loader = importlib.machinery.SourceFileLoader("check_config_cache", path)
    spec = importlib.util.spec_from_loader("check_config_cache", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


check_config = load()


def entries(name: str) -> list[dict[str, Any]]:
    return yaml.safe_load((GROUPS / f"{name}.yaml").read_text())["model_list"]


def test_the_anthropic_groups_cache_the_system_prompt_and_the_last_message() -> None:
    anthropic = [
        e for e in entries("providers") if e["litellm_params"]["model"].startswith("anthropic/")
    ]
    assert {e["model_name"] for e in anthropic} == {"default", "fast"}
    for entry in anthropic:
        assert entry["litellm_params"]["cache_control_injection_points"] == [
            {"location": "message", "role": "system"},
            {"location": "message", "index": -1},
        ]


def test_the_upstream_groups_get_no_breakpoints() -> None:
    for entry in entries("upstream"):
        assert "cache_control_injection_points" not in entry["litellm_params"]


def test_the_aliases_in_config_get_none_either() -> None:
    config = yaml.safe_load((STACKR / "deploy" / "litellm" / "config.yaml").read_text())
    for entry in config["model_list"]:
        assert "cache_control_injection_points" not in entry["litellm_params"]


@pytest.fixture
def stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of what the check reads, which it reads in place of the real files."""
    shutil.copy(STACKR / "compose.yaml", tmp_path / "compose.yaml")
    shutil.copytree(STACKR / "deploy" / "litellm", tmp_path / "deploy" / "litellm")
    monkeypatch.setattr(check_config, "ROOT", tmp_path)
    return tmp_path / "deploy" / "litellm" / "groups"


def rewrite(groups: Path, name: str, change: Any) -> None:
    path = groups / f"{name}.yaml"
    chosen = yaml.safe_load(path.read_text())
    change(chosen["model_list"])
    path.write_text(yaml.safe_dump(chosen))


def test_the_check_passes_on_the_real_files(stack: Path) -> None:
    assert check_config.check_litellm() == []


def test_an_anthropic_group_without_breakpoints_is_reported(stack: Path) -> None:
    rewrite(
        stack,
        "providers",
        lambda groups: groups[1]["litellm_params"].pop("cache_control_injection_points"),
    )
    [problem] = check_config.check_litellm()
    assert problem.startswith("groups/providers.yaml's 'fast' needs the prompt-cache breakpoints")


def test_breakpoints_on_another_provider_are_reported(stack: Path) -> None:
    def add(groups: list[dict[str, Any]]) -> None:
        groups[0]["litellm_params"]["cache_control_injection_points"] = check_config.CACHE_POINTS

    rewrite(stack, "upstream", add)
    [problem] = check_config.check_litellm()
    assert "'default' isn't Anthropic" in problem


def test_a_point_may_carry_a_ttl(stack: Path) -> None:
    def add_ttl(groups: list[dict[str, Any]]) -> None:
        for point in groups[0]["litellm_params"]["cache_control_injection_points"]:
            point["control"] = {"type": "ephemeral", "ttl": "1h"}

    rewrite(stack, "providers", add_ttl)
    assert check_config.check_litellm() == []


# The points as LiteLLM types them: check-config's CACHE_POINTS (asserted equal below).
POINTS = [
    CacheControlMessageInjectionPoint(location="message", role="system", index=None, control=None),
    CacheControlMessageInjectionPoint(location="message", role=None, index=-1, control=None),
]


def test_the_typed_points_are_the_checks() -> None:
    given = [{key: value for key, value in point.items() if value is not None} for point in POINTS]
    assert given == check_config.CACHE_POINTS


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
