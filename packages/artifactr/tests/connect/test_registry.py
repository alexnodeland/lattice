"""A connected app's risks, mapped to capability tiers (lattice RFC-0011, artifactr ADR-0099)."""

from typing import get_args

from artifactr.connect import PROTECTED, TIERS, Risk


def test_each_risk_has_a_tier_but_host_which_is_never_offered() -> None:
    assert set(TIERS) == set(get_args(Risk))
    assert dict(TIERS) == {
        "read": "read",
        "edit": "write",
        "code": "run_code",
        "network": "outbound",
        "host": None,
    }


def test_the_protected_risks_are_those_that_run_code_or_reach_outside() -> None:
    assert {risk for risk, tier in TIERS.items() if tier in {"run_code", "outbound"}} == PROTECTED
