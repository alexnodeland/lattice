"""Which of the forms' integrations are on in a workspace, on lattice's shared port (ADR-0080).

Forms, dashboards and mini apps are lattice's integrations ``ui:forms``, ``ui:dashboards`` and
``ui:mini-apps``, declared in lattice-core's :data:`~lattice_core.integrations.KNOWN`, the last
off by default. An application asks lattice-core's ``Integrations`` port about them, as it asks
about every integration (lattice ADR-0027): grantr's store, or ``Defaults`` without one.

- **The artifacts are gated by artifactr's gate** (ADR-0081): give
  ``Workspaces(gate=integration_gate(integrations, ui_key_of))``, and making or changing a form,
  a submission, a dashboard or an app while its integration is off is refused as
  ``not_enabled``.
- **The agent's tools are offered** only while their integration is on: ``ui_tools``'s
  ``integrations``.
- **An answer to ``ask_form``,** which changes no artifact the gate could see, is refused by
  ``ui_checks``'s ``integrations`` while forms are off, as ``not_enabled`` too.
"""

from collections.abc import Mapping
from typing import Final, Literal

from pydantic import JsonValue

__all__ = ["DASHBOARDS", "FORMS", "MINI_APPS", "IntegrationKey", "ui_key_of"]

FORMS: Final = "ui:forms"
"""Forms: ``ask_form``, ``create_form``, and the submissions and answers people send."""

DASHBOARDS: Final = "ui:dashboards"
"""Dashboards: ``show_dashboard`` and ``update_dashboard``, and the dashboards they write."""

MINI_APPS: Final = "ui:mini-apps"
"""Mini apps, RFC-0005's second phase, off by default: apps, and the submissions sent to them."""

IntegrationKey = Literal["ui:forms", "ui:dashboards", "ui:mini-apps"]
"""The keys of forms, dashboards and mini apps."""

_KINDS: Final[Mapping[str, str]] = {"form": FORMS, "dashboard": DASHBOARDS, "app": MINI_APPS}


def ui_key_of(kind: str, data: Mapping[str, JsonValue]) -> str | None:
    """The integration that governs an artifact, for artifactr's ``integration_gate``.

    A form and a submission to one are forms', a dashboard is dashboards', and an app and a
    submission to one are mini apps'. Any other kind is none of these.
    """
    if kind == "submission":
        return FORMS if data.get("form_id") is not None else MINI_APPS
    return _KINDS.get(kind)
