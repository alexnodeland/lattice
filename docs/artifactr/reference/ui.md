# artifactr.ui

Forms and dashboards in the chat, behind the `forms` extra: `uv add "artifactr-ai[forms]"` ([ADR-0074](../adr/0074-forms-and-dashboards-in-artifactr-ui-behind-the-forms-extra.md), [the guide](../guides/forms-and-dashboards.md)). relayr bridges what people send into reflexr in `relayr.ui` ([relayr's reference](../../relayr/reference.md#relayrui)).

::: artifactr.ui
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## artifactr.ui.schema

The form schema: a JSON Schema 2020-12 subset, its hints and its validator ([ADR-0076](../adr/0076-the-form-schema-an-allow-list-compiled-to-pydantic.md), [ADR-0077](../adr/0077-formats-and-sizes-checked-by-artifactrs-own-code.md)).

::: artifactr.ui.schema
    options:
      show_root_heading: false
      show_root_toc_entry: false

## artifactr.ui.types

The `form`, `submission`, `dashboard` and `app` kinds, and `ask_form`'s request.

::: artifactr.ui.types
    options:
      show_root_heading: false
      show_root_toc_entry: false

## artifactr.ui.ids

A submission's derived id.

::: artifactr.ui.ids
    options:
      show_root_heading: false
      show_root_toc_entry: false

## artifactr.ui.integrations

Which integrations are on in a workspace ([ADR-0080](../adr/0080-integrations-on-or-off-per-workspace.md)).

::: artifactr.ui.integrations
    options:
      show_root_heading: false
      show_root_toc_entry: false

## artifactr.ui.checks

The checks for `Workspaces(checks=...)` ([ADR-0075](../adr/0075-forms-refused-at-the-boundary-through-the-checks.md)).

::: artifactr.ui.checks
    options:
      show_root_heading: false
      show_root_toc_entry: false

## artifactr.ui.agent

The agent's toolset ([ADR-0078](../adr/0078-the-agents-toolset-for-forms-and-no-apps-yet.md)).

::: artifactr.ui.agent
    options:
      show_root_heading: false
      show_root_toc_entry: false

## artifactr.ui.wire

The wire schema, committed as `schemas/artifactr_ui.v1.json`.

::: artifactr.ui.wire
    options:
      show_root_heading: false
      show_root_toc_entry: false
