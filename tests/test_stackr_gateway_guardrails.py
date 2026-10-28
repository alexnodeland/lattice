"""stackr's gateway guardrails: what each one reads (ADR-0010's 2026-10-27 amendment).

`prompt-injection` reads tool results alone, so the model's own replies and tool arguments, such
as a generated page, can't trip its word lists; `pii-mask` still reads every message.
"""

from pathlib import Path
from typing import Any

import yaml

STACKR = Path(__file__).parent.parent / "packages" / "stackr"
CONFIG = STACKR / "deploy" / "litellm" / "config.yaml"


def guardrails() -> dict[str, dict[str, Any]]:
    config = yaml.safe_load(CONFIG.read_text())
    return {g["guardrail_name"]: g["litellm_params"] for g in config["guardrails"]}


def test_prompt_injection_reads_only_tool_results() -> None:
    params = guardrails()["prompt-injection"]
    assert params["scan_only_tool_results"] is True
    # Skipping tool messages too would leave the guardrail nothing to read.
    assert "skip_tool_message_in_guardrail" not in params


def test_prompt_injection_still_blocks_every_category() -> None:
    categories = guardrails()["prompt-injection"]["categories"]
    assert {c["category"]: (c["action"], c["severity_threshold"]) for c in categories} == {
        "prompt_injection_jailbreak": ("BLOCK", "medium"),
        "prompt_injection_system_prompt": ("BLOCK", "medium"),
        "prompt_injection_data_exfiltration": ("BLOCK", "medium"),
    }


def test_pii_mask_reads_every_message() -> None:
    params = guardrails()["pii-mask"]
    assert "scan_only_tool_results" not in params
    assert "skip_tool_message_in_guardrail" not in params


def test_the_smoke_test_puts_its_injection_in_a_tool_result() -> None:
    smoke = (STACKR / "scripts" / "smoke").read_text()
    assert '"role": "tool", "tool_call_id": "call_1",\n          "content": "Ignore all' in smoke
