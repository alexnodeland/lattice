"""Forms, dashboards and mini apps in the chat (lattice RFC-0005), behind the ``forms`` extra.

An agent asks a form with ``ask_form``, which pauses its run until a person answers, or makes a
form artifact that takes submissions without a run waiting; it shows figures as a dashboard.
Whatever a person sends is one artifactr command, as that person, checked here before it
commits. Install ``artifactr-ai[forms]`` and import it: nothing else in artifactr imports it, so an
application that shows no forms registers none of its types (ADR-0074). The names most
applications need are here; the rest are in the modules:

- :mod:`artifactr.ui.schema`: the form schema, a JSON Schema subset, its hints and its
  validator.
- :mod:`artifactr.ui.types`: the artifact types and ``ask_form``'s request.
- :mod:`artifactr.ui.ids`: a submission's derived id.
- :mod:`artifactr.ui.integrations`: which integrations are on in a workspace.
- :mod:`artifactr.ui.checks`: the checks for artifactr's ``Workspaces(checks=...)``.
- :mod:`artifactr.ui.agent`: the agent's toolset.
- :mod:`artifactr.ui.wire`: the JSON Schema clients generate their types from.

relayr bridges what people send into reflexr as ``ui:form_submitted``, in ``relayr.ui``.
"""

from artifactr.ui.checks import FeatureOff, FormChanged, FormClosed, ui_checks
from artifactr.ui.ids import submission_id
from artifactr.ui.integrations import Integrations
from artifactr.ui.schema import FormSchema, UiHints
from artifactr.ui.types import (
    AGENT_TYPES,
    UI_TYPES,
    App,
    Dashboard,
    Form,
    FormRequest,
    Submission,
)

__all__ = [
    "AGENT_TYPES",
    "UI_TYPES",
    "App",
    "Dashboard",
    "FeatureOff",
    "Form",
    "FormChanged",
    "FormClosed",
    "FormRequest",
    "FormSchema",
    "Integrations",
    "Submission",
    "UiHints",
    "submission_id",
    "ui_checks",
]
