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
