"""lattice's approval policy: who must approve a call, from the settings (lattice ADR-0038).

A tier the ``approve:tiers`` setting names asks a person; an ``admin_high`` capability asks the
caller's own confirmation, or a different approver where the gate or the
``admin-high:different-approver`` setting says so; a tainted outbound call asks a different
approver.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from lattice_core.approvals import (
    ADMIN_HIGH_DIFFERENT,
    ANSWER_APPROVAL,
    Answerers,
    ApprovalPolicy,
    SettingsPolicy,
    admin_high_approvers,
)
from lattice_core.capabilities import (
    CallContext,
    Caller,
    Capability,
    Gate,
    PersonCaller,
    RunCaller,
    Scope,
)
from lattice_core.settings import (
    APPROVE_TIERS,
    KNOWN_SETTINGS,
    Setting,
    SettingsDefaults,
    Superset,
    Value,
    registry,
)
from lattice_core.taint import Cause, Clean, Taint, Tainted

HERE = Scope(tenant_id="acme", workspace_id="docs")
ALEX = PersonCaller(id="alex")
RUN = RunCaller(id="run_1", agent="helper", on_behalf_of="alex")
ALONE = RunCaller(id="run_2", agent="nightly")
TAINTED = Tainted(
    causes=(Cause(capability="web.fetch", at=datetime(2026, 11, 1, tzinfo=UTC)),),
)


def capability(**changes: Any) -> Capability:
    fields: dict[str, Any] = {
        "name": "artifactr.edit_text",
        "version": "1.0.0",
        "description": "Edit an artifact's text.",
        "input_schema": {"type": "object"},
        "output_schema": None,
        "provider": "command",
        "tier": "write",
        "effects": frozenset[str](),
        "reversibility": "compensable",
        "gate": Gate(integration=None, action="artifactr:edit_artifact"),
    }
    return Capability.model_validate(fields | changes)


DELETE = capability(
    name="grantr.delete_tenant",
    description="Delete the tenant.",
    tier="write",
    reversibility="irreversible",
    gate=Gate(integration=None, action="grantr:delete_tenant"),
    risk_class="admin_high",
)
REVOKE = capability(
    name="grantr.revoke_key",
    description="Revoke a key.",
    gate=Gate(integration=None, action="grantr:revoke_key"),
    risk_class="admin_high",
)


def context(caller: Caller = RUN, taint: Taint | None = None) -> CallContext:
    return CallContext(
        scope=HERE,
        caller=caller,
        taint=Clean() if taint is None else taint,
        correlation_id="turn_1",
        surface="portalr",
    )


KNOWN = registry(*KNOWN_SETTINGS.values(), admin_high_approvers([DELETE, REVOKE, capability()]))


def policy(**operator: object) -> SettingsPolicy:
    return SettingsPolicy(SettingsDefaults(KNOWN, operator))


def test_it_is_an_approval_policy() -> None:
    assert isinstance(policy(), ApprovalPolicy)


def test_the_admin_high_setting_names_only_admin_high_capabilities() -> None:
    setting = KNOWN[ADMIN_HIGH_DIFFERENT]
    assert setting.kind == Superset(frozenset({"grantr.delete_tenant", "grantr.revoke_key"}))
    assert (setting.default, setting.lowest) == ((), "tenant"), "the operator's to set, or more"
    assert admin_high_approvers([]).kind == Superset(frozenset()), "an application with none"


async def test_a_tier_the_setting_doesnt_name_asks_no_one() -> None:
    assert await policy().needed(capability(), context()) is None, "write isn't asked by default"
    assert await policy().needed(capability(tier="read"), context()) is None


async def test_a_tier_the_setting_names_asks_the_person_or_an_approver() -> None:
    outbound = capability(tier="outbound", effects=frozenset({"sends_out"}))
    assert await policy().needed(outbound, context()) == Answerers(
        action=ANSWER_APPROVAL, subjects=frozenset({"alex"})
    ), "the person the run acts for, or whoever holds the action"
    assert await policy().needed(outbound, context(ALONE)) == Answerers(action=ANSWER_APPROVAL)
    asked = policy(**{APPROVE_TIERS: ["write", "outbound", "run_code"]})
    assert await asked.needed(capability(), context(ALEX)) == Answerers(
        action=ANSWER_APPROVAL, subjects=frozenset({"alex"})
    ), "the operator asks on writes too"


async def test_the_gate_or_a_tainted_outbound_call_asks_a_different_approver() -> None:
    gated = capability(
        tier="run_code",
        gate=Gate(integration=None, action="artifactr:run_connected_code", different_approver=True),
    )
    different = Answerers(action=ANSWER_APPROVAL, different_approver=True)
    assert await policy().needed(gated, context()) == different
    outbound = capability(tier="outbound", effects=frozenset({"sends_out"}))
    assert await policy().needed(outbound, context(taint=TAINTED)) == different
    code = capability(tier="run_code")
    assert await policy().needed(code, context(taint=TAINTED)) == Answerers(
        action=ANSWER_APPROVAL, subjects=frozenset({"alex"})
    ), "taint asks a different approver only of a call that reaches outside"


async def test_admin_high_asks_the_callers_own_confirmation() -> None:
    confirm = Answerers(subjects=frozenset({"alex"}), confirmation=True)
    assert await policy().needed(DELETE, context(ALEX)) == confirm
    assert await policy().needed(DELETE, context(RUN)) == confirm, "the person a run acts for"
    nobody = await policy().needed(DELETE, context(ALONE))
    assert nobody == Answerers(action=ANSWER_APPROVAL), "no person to confirm: an approver"
    outside = policy(**{APPROVE_TIERS: []})
    assert await outside.needed(DELETE, context(ALEX)) == confirm, "whatever the tiers"


async def test_admin_high_asks_a_different_approver_where_the_setting_or_gate_says() -> None:
    different = Answerers(action=ANSWER_APPROVAL, different_approver=True)
    listed = policy(**{ADMIN_HIGH_DIFFERENT: ["grantr.delete_tenant"]})
    assert await listed.needed(DELETE, context(ALEX)) == different
    assert await listed.needed(REVOKE, context(ALEX)) == Answerers(
        subjects=frozenset({"alex"}), confirmation=True
    ), "only the actions it lists"
    gated = DELETE.model_copy(
        update={
            "gate": Gate(integration=None, action="grantr:delete_tenant", different_approver=True)
        }
    )
    assert await policy().needed(gated, context(ALEX)) == different


async def test_a_custom_action_names_who_answers() -> None:
    custom = SettingsPolicy(SettingsDefaults(KNOWN), action="acme:approve")
    outbound = capability(tier="outbound", effects=frozenset({"sends_out"}))
    assert await custom.needed(outbound, context(ALONE)) == Answerers(action="acme:approve")


class Numbers:
    """A store whose every setting holds a number: never what a setting of names holds."""

    async def value(self, _tenant_id: str, _workspace_id: str | None, _key: str, /) -> Value:
        return 3


class Undeclared:
    """A store that knows no admin-high setting, as an application that didn't declare it."""

    def __init__(self) -> None:
        self._known: dict[str, Setting] = dict(KNOWN_SETTINGS)

    async def value(self, _tenant_id: str, _workspace_id: str | None, key: str, /) -> Value:
        return self._known[key].default


async def test_a_setting_that_isnt_names_or_isnt_declared_refuses_the_call() -> None:
    with pytest.raises(TypeError, match="approve:tiers holds names"):
        await SettingsPolicy(Numbers()).needed(capability(), context())
    with pytest.raises(TypeError, match="admin-high:different-approver holds names"):
        await SettingsPolicy(Numbers()).needed(DELETE, context())
    with pytest.raises(KeyError):
        await SettingsPolicy(Undeclared()).needed(DELETE, context())
