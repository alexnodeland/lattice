"""Settings, narrowed: how four layers decide a setting's value in a workspace (lattice ADR-0030).

A setting's default is the registry's, which the operator's value, in the deployment's
configuration, replaces. A tenant's admins, and then a workspace's, may each only narrow the
layer above: a number lowered, a subset shrunk. A stored value that would widen its layer, after
the operator lowered the ceiling under it, is kept but clamped: the narrower wins, and the value
is shown as clamped. A value a changed registry no longer takes is kept narrowed to it, never
widened, and a stored key no registry declares any more is never applied, and is listed as
unknown.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from grantr.core.subjects import Subject
from lattice_core.settings import IntRange, Setting, Tier, Value

type Wire = int | list[str]
"""A setting's value as JSON carries it: a whole number, or names, sorted."""


def wire(value: Value) -> Wire:
    """A value as JSON carries it."""
    return list(value) if isinstance(value, tuple) else value


class SettingRow(BaseModel):
    """One level's setting as stored: its value (``None`` once unset), version, who and when.

    Unsetting keeps the row, with no value, so its version keeps counting and a client that read
    an older one is told it is stale.
    """

    model_config = ConfigDict(frozen=True)

    value: Wire | None
    version: int
    by: Subject
    at: datetime
    """When it was set: its audit entry's time."""

    profile_version: str | None = None
    """The profile it was set under, for a later rollback to judge it by; none yet."""


class SettingLayer(BaseModel):
    """One level's setting as an admin reads it."""

    model_config = ConfigDict(frozen=True)

    value: Wire
    version: int
    by: Subject
    at: datetime
    clamped: bool
    """Whether a layer above has since narrowed below it, so the narrower applies instead."""


class SettingKind(BaseModel):
    """What a setting's value is: a whole number within bounds, or some of a set of names."""

    model_config = ConfigDict(frozen=True)

    type: Literal["int_range", "subset"]
    low: int | None = None
    high: int | None = None
    universe: list[str] | None = None


class SettingState(BaseModel):
    """A setting as an admin reads it, on the tenant or in a workspace."""

    model_config = ConfigDict(frozen=True)

    key: str
    description: str
    kind: SettingKind
    default: Wire
    lowest: Tier
    """The lowest tier that may set it: ``operator`` for configuration alone."""

    operator: Wire | None
    """The operator's value, which replaces the default; ``None`` if it sets none."""

    tenant: SettingLayer | None
    """The tenant's setting; ``None`` if unset."""

    workspace: SettingLayer | None
    """The workspace's setting; ``None`` if unset, and on the tenant."""

    version: int
    """The version of this level's setting, which a change names: 0 if it was never set."""

    ceiling: Wire
    """The widest value this level may set: the layer above's."""

    ceiling_set_by: Literal["default", "operator", "tenant"]
    """Which layer the ceiling is."""

    effective: Wire
    """Its value in the workspace; on the tenant, in a workspace that sets nothing."""


class SettingsView(BaseModel):
    """Every setting as an admin reads it, and the stored keys no registry declares any more."""

    model_config = ConfigDict(frozen=True)

    settings: list[SettingState]
    unknown: list[str]
    """Keys set here that no setting declares: never applied."""


def stored(setting: Setting, row: SettingRow | None) -> Value | None:
    """A row's value as the registry keeps it now, or ``None`` if it is unset.

    A value an earlier registry took is never widened by a change of the registry: a number is
    clamped into today's bounds, names it no longer knows are dropped, and a value of another
    type is the setting's floor.
    """
    if row is None or row.value is None:
        return None
    return setting.kept(row.value)


def kind(setting: Setting) -> SettingKind:
    """A setting's kind, as JSON carries it."""
    if isinstance(setting.kind, IntRange):
        return SettingKind(type="int_range", low=setting.kind.low, high=setting.kind.high)
    return SettingKind(type="subset", universe=sorted(setting.kind.universe))


def state(
    setting: Setting,
    *,
    operator: Value | None,
    tenant: SettingRow | None,
    workspace: SettingRow | None,
    in_workspace: bool,
) -> SettingState:
    """A setting's state on the tenant, or in a workspace, worked out from its layers."""
    base = setting.default if operator is None else operator
    on_tenant_value = stored(setting, tenant)
    on_tenant = setting.narrow(base, on_tenant_value)
    in_workspace_value = stored(setting, workspace) if in_workspace else None
    effective = setting.narrow(on_tenant, in_workspace_value)
    if in_workspace:
        ceiling = on_tenant
        set_by = "tenant" if on_tenant_value is not None and on_tenant != base else _top(operator)
        version = 0 if workspace is None else workspace.version
    else:
        ceiling, set_by = base, _top(operator)
        version = 0 if tenant is None else tenant.version
    return SettingState(
        key=setting.key,
        description=setting.description,
        kind=kind(setting),
        default=wire(setting.default),
        lowest=setting.lowest,
        operator=None if operator is None else wire(operator),
        tenant=_layer(setting, tenant, on_tenant_value, base),
        workspace=_layer(setting, workspace, in_workspace_value, on_tenant)
        if in_workspace
        else None,
        version=version,
        ceiling=wire(ceiling),
        ceiling_set_by=set_by,
        effective=wire(effective),
    )


def _top(operator: Value | None) -> Literal["default", "operator"]:
    return "default" if operator is None else "operator"


def _layer(
    setting: Setting, row: SettingRow | None, value: Value | None, above: Value
) -> SettingLayer | None:
    if row is None or value is None:
        return None
    return SettingLayer(
        value=wire(value),
        version=row.version,
        by=row.by,
        at=row.at,
        clamped=not setting.within(value, above),
    )
