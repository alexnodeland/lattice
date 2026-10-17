"""How three levels decide whether an integration is on: the laws, and every case of them."""

from datetime import UTC, datetime
from itertools import product

from hypothesis import given
from hypothesis import strategies as st

from grantr.core import IntegrationSetting, IntegrationState, User, effective

levels = st.none() | st.booleans()
"""A tenant's or a workspace's setting: unset, on or off."""


def nearest(installed: bool, default: bool, tenant: bool | None, workspace: bool | None) -> bool:
    """The rule as the ADR words it: under the ceilings, the nearest level that is set decides."""
    ceilings = (installed, tenant is not False)
    decides = next(level for level in (workspace, tenant, default) if level is not None)
    return all(ceilings) and decides


def test_every_case_is_the_nearest_set_level_under_the_ceilings() -> None:
    cases = list(product([False, True], [False, True], [None, False, True], [None, False, True]))
    assert len(cases) == 36
    for installed, default, tenant, workspace in cases:
        assert effective(
            installed=installed, default=default, tenant=tenant, workspace=workspace
        ) == nearest(installed, default, tenant, workspace), (installed, default, tenant, workspace)


@given(st.booleans(), levels)
def test_off_at_the_deployment_or_the_tenant_is_a_ceiling(
    default: bool, workspace: bool | None
) -> None:
    for installed, tenant in ((False, None), (False, True), (False, False), (True, False)):
        assert not effective(
            installed=installed, default=default, tenant=tenant, workspace=workspace
        )


@given(st.booleans(), levels)
def test_an_unset_workspace_inherits_the_tenant_or_the_default(
    default: bool, tenant: bool | None
) -> None:
    inherited = default if tenant is None else tenant
    for installed in (False, True):
        assert effective(
            installed=installed, default=default, tenant=tenant, workspace=None
        ) == effective(installed=installed, default=default, tenant=tenant, workspace=inherited)


@given(st.booleans(), st.booleans(), st.booleans())
def test_an_unset_tenant_leaves_the_ceiling_open(
    installed: bool, default: bool, workspace: bool
) -> None:
    """With the workspace set, an unset tenant is an on one; unset beneath, it is the default."""
    assert effective(
        installed=installed, default=default, tenant=None, workspace=workspace
    ) == effective(installed=installed, default=default, tenant=True, workspace=workspace)
    assert effective(installed=installed, default=default, tenant=None, workspace=None) == (
        effective(installed=installed, default=default, tenant=default, workspace=None)
    )


@given(st.booleans(), st.sampled_from([None, True]), st.booleans())
def test_a_workspaces_own_setting_wins_under_open_ceilings(
    default: bool, tenant: bool | None, workspace: bool
) -> None:
    assert effective(installed=True, default=default, tenant=tenant, workspace=workspace) == (
        workspace
    )


@given(st.booleans(), st.booleans(), levels, levels)
def test_a_state_is_on_as_its_levels_say(
    installed: bool, default: bool, tenant: bool | None, workspace: bool | None
) -> None:
    def setting(on: bool | None) -> IntegrationSetting | None:
        at = datetime(2026, 10, 17, tzinfo=UTC)
        return None if on is None else IntegrationSetting(on=on, by=User(id="alice"), at=at)

    state = IntegrationState.of(
        "excalidraw",
        description="Diagrams.",
        default=default,
        installed=installed,
        tenant=setting(tenant),
        workspace=setting(workspace),
    )
    assert state.enabled == nearest(installed, default, tenant, workspace)
