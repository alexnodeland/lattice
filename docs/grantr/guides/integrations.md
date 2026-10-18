# Integrations, switched per workspace

Every integration lattice adds can be turned on or off for one workspace: the trackers, native files, forms, dashboards and mini apps, Markdown's add-ons, and diagrams. Each package asks one port before an integration acts, `lattice_core.integrations.Integrations`, and grantr answers it from a table of its own, with every switch in its audit log ([lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md), [ADR-0034](../adr/0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md)).

## What is on

An integration is on in a workspace only where all three levels leave it on:

```text
on = installed and tenant != off and (workspace ?? tenant ?? default)
```

| Level | Who sets it | What it can do |
|---|---|---|
| The deployment | Its configuration: `Grants(installed=...)` | Install an integration or not. One it doesn't install is off everywhere |
| The tenant | Its owners and admins | Turn it on or off for every workspace. Off is a ceiling |
| The workspace | Its admins, and the tenant's | Turn it on or off here |

A level with nothing set inherits the one above, and the integration's default is what it is where no one has set it. So mini apps, off by default, can be turned on for one workspace by its admin, unless the tenant turned them off.

## The integrations

lattice declares its integrations in one registry, `lattice_core.integrations.KNOWN`:

| Key | Default | What |
|---|---|---|
| `tracker:plane`, `tracker:vikunja` | On | relayr's trackers ([RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md)) |
| `files:wordcraft` | On | Native files edited in WordCraft ([RFC-0003](../../rfcs/0003-native-files-as-artifacts.md)) |
| `ui:forms`, `ui:dashboards` | On | Forms and dashboards in the chat ([RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md)) |
| `ui:mini-apps` | Off | Mini apps, RFC-0005's second phase |
| `excalidraw` | On | Diagrams ([RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)) |
| `markdown:math` | On | Formulas in Markdown |
| `markdown:mermaid` | Off | Mermaid's diagrams, parked while Mermaid can't draw under portalr's policy |

An application with an integration of its own declares it once, with its default and a sentence for the admin who switches it, and gives grantr the registry with it:

```python
from grantr import Grants
from lattice_core.integrations import KNOWN, Integration, registry

CRM = Integration("crm:hubspot", default=False, description="HubSpot: deals as artifacts.")

grants = Grants(
    storage,
    catalogs=[ARTIFACTR, REFLEXR],
    integrations=registry(*KNOWN.values(), CRM),
    installed={"tracker:plane", "ui:forms", "ui:dashboards", "crm:hubspot"},
)
```

portalr's admin lists it with the others, with no change of its own.

## Switching

Switching, and reading how each level is set, needs `grantr:manage_integrations` at its level, which a tenant's `owner` and `admin` hold on the tenant and a workspace's `admin` holds on the workspace:

```python
await grants.set_integration("acme", "ui:forms", False, by=ALICE)  # the tenant
await grants.set_integration("acme", "ui:mini-apps", True, workspace="lab", by=BOB)
await grants.set_integration("acme", "ui:mini-apps", None, workspace="lab", by=BOB)  # inherit

await grants.integrations("acme", workspace="lab", by=BOB)  # each one's levels, and who set them
await grants.integrations_enabled("acme", "lab", by=CAROL)  # {"ui:forms": False, ...}
```

A key no registry declares is `Invalid`. Each real change is one `integration_set` entry in the tenant's audit log, in the change's transaction; a switch to what it already is records nothing. The admin API has the same:

| Route | Needs |
|---|---|
| `GET /tenants/{tenant}/integrations`, `PUT /tenants/{tenant}/integrations/{key}` | `grantr:manage_integrations` on the tenant |
| `GET /tenants/{tenant}/workspaces/{workspace}/integrations`, `PUT /tenants/{tenant}/workspaces/{workspace}/integrations/{key}` | `grantr:manage_integrations` on the workspace |
| `GET /tenants/{tenant}/workspaces/{workspace}/enabled-integrations` | Any `open` on the workspace |

A `PUT`'s body is `{"on": true}`, `{"on": false}`, or `{"on": null}` to inherit. portalr's admin has a page for it, Integrations, under each tenant, for its owners and admins: it shows where each state comes from, and who set it and when ([portalr's admin guide](../../portalr/guides/admin.md)).

## Asking

`Grants` is the port: `await grants.is_enabled(tenant_id, workspace_id, key)` checks no one, and answers off for a key it doesn't know or doesn't install, and for a store it can't read. Each call reads the tenant's settings and the workspace's; an application that asks often caches.

**artifactr** refuses what an integration governs while it is off, through `Workspaces(gate=...)`. The gate runs after the command's target is resolved, so a hidden artifact is still `NotFound`, and before `authorize`, so off is `NotEnabled`, never `Forbidden` ([artifactr ADR-0081](../../artifactr/adr/0081-a-gate-before-access-integrations-switched-off-answer-not-enabled.md)). `integration_gate` builds one from the port and a map from an artifact's kind and data to its key:

```python
from artifactr.workspace import Workspaces, integration_gate

hooks = grants.hooks(subject_of)

KEYS = {"word_document": "files:wordcraft", "excalidraw_diagram": "excalidraw"}

workspaces = Workspaces(
    storage,
    authorize=hooks.authorize,
    hidden=hooks.hidden,
    gate=integration_gate(grants, lambda kind, data: KEYS.get(kind)),
)
```

While one is off, creating, editing, proposing and accepting are refused for every command, on every surface, REST (409, `not_enabled`), MCP, the WebSocket and the agent's runs. Reads, archiving and rejecting a proposal still work, so what exists stays readable.

**relayr's trackers** take the port as their `integrations`: `Trackers(..., integrations=grants)`.

## A provider that narrows

The port answers yes or no, so a feature-flag service can only narrow what grantr says: an `Integrations` of the application's that asks grantr first and the service only when grantr says on. None is built, and it never turns on what an admin turned off.

```python
class Narrowed:
    def __init__(self, grants: Grants, flags: Flags) -> None:
        self._grants, self._flags = grants, flags

    async def is_enabled(self, tenant_id: str, workspace_id: str, key: str, /) -> bool:
        return await self._grants.is_enabled(tenant_id, workspace_id, key) and await self._flags.on(
            tenant_id, workspace_id, key
        )
```

## Adopting the port

Three seams came before the port. One is still to move to it:

- **relayr's `Enabled`** has gone: its trackers take the port, and `relayr.integrations.ALWAYS` is the answer with no store, every integration on ([relayr ADR-0033](../../relayr/adr/0033-the-tracker-port-and-runs-that-write-to-it-once.md)'s amendment).
- **stackr's template** is to give `Grants` the deployment's `installed`, from its questions, and to wire `integration_gate` and relayr's `enabled` to it. Until then, an application it generates installs every integration, with each at its default.

artifactr's forms and dashboards were built on the port: `ui_key_of` names their keys for `integration_gate`, and `ui_tools` and `ui_checks` take the port ([artifactr ADR-0080](../../artifactr/adr/0080-integrations-on-or-off-per-workspace.md)).
