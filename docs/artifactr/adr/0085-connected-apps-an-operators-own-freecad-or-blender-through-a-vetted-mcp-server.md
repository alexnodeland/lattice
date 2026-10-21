# ADR-0085: Connected apps: an operator's own FreeCAD or Blender, through a vetted MCP server

**Status:** Proposed
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Beside:** native files' [ADR-0014](../files/adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md) (FreeCAD) and its Blender sibling, which stay as they are

## Context

Native files run FreeCAD and Blender in the worker, on a curated script dialect, with no Python an agent or a file brings ([files ADR-0014](../files/adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md)). That path is for files anyone may upload, hostile ones included. The owner asked for a second path, off by default: an **operator** connects a FreeCAD or Blender **they run themselves**, a desktop window or a trusted headless instance, through its community MCP server, so the agent gets the app's richer tools and a live viewport.

What the servers are, read from their source on 2026-10-20 and not run:

| Server | Licence, version, last push | Transport | Tools, by risk |
|---|---|---|---|
| [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) | MIT, v0.1.27, 2026-10-13 | `uvx freecad-mcp`, an MCP server on stdio that calls an add-on's XML-RPC server in the FreeCAD GUI on port 9875; the add-on's settings default to `allowed_ips=127.0.0.1`, `remote_enabled=false`, and `auth_token=""`, no authentication (`addon/FreeCADMCP/rpc_server/settings.py`), a token optional through `FREECAD_MCP_TOKEN` | read: `list_documents`, `get_objects`, `get_object`, `get_parts_list`, `get_view` (a PNG), `get_rpc_status`, `get_async_status`; edit: `create_document`, `create_object`, `edit_object`, `delete_object`; code: `execute_code`, `execute_code_async`; code on the **runner's** host: `execute_code_headless` (a fresh FreeCAD where the MCP server runs, not the operator's app); files: `reload_document`, `insert_part_from_library`; heavy: `run_fem_analysis` |
| [spkane/freecad-addon-robust-mcp-server](https://github.com/spkane/freecad-addon-robust-mcp-server) | MIT, 2026-10-19 | stdio or HTTP; XML-RPC on 9875 (neka-nat compatible) or JSON-RPC on 9876, or FreeCAD embedded in the server's process | 150+; code: `execute_python`, `safe_execute`, the macro tools (`run_macro`, `create_macro`: Python kept on disk); files: `open_document`, `save_document`, `import_*`, `export_*`, `spreadsheet_import_csv`/`_export_csv`; leaks: `get_mcp_server_environment` |
| [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) | MIT, 2.2.2, 2026-10-20 | `uvx blender-mcp`, stdio, to an add-on's socket in Blender on `localhost:9876` (`BLENDER_HOST`, `BLENDER_PORT`), no authentication | read: `get_scene_info`, `get_addon_status`, `look`, the viewport's `viewport_*`; code: `execute_blender_code`; network: `search_assets`, `import_asset`, `generate_3d` (Poly Haven, Sketchfab, Hyper3D and others); data collection: `disable_telemetry`, `record_trajectory_feedback`. A minimal anonymous usage record is sent unless `DISABLE_TELEMETRY=true` |
| [Blender Lab's blender_mcp](https://projects.blender.org/lab/blender_mcp) | GPL-3.0, 1.0.2, 2026-09-29; Blender 5.1 or newer | `blmcp` on stdio to an add-on's socket on `localhost:9876` (`BLENDER_MCP_HOST`, `BLENDER_MCP_PORT`), no authentication | **every** tool sends Python to the add-on (`tools_helpers/connection.py`); the read tools are the server's own fixed scripts. code: `execute_blender_code`, `execute_blender_code_for_cli`; files on the runner's host: every `*_for_cli` (opens a `blend_file` in a background Blender), `render_*_to_path`. Its own page warns it "will execute LLM generated code in Blender without any guards" |

Three facts follow, and the design rests on them:

1. **The app's port is a code-execution endpoint for any local process.** Every add-on accepts Python on its socket, without authentication by default. Whatever lattice filters governs only what the *agent* asks for, never what the socket allows. The connected app is as safe as the machine it runs on.
2. **A "read" tool is the server's code, run in the app.** Vetting a server is trusting its shipped scripts at a pinned version, not inspecting a protocol.
3. **Some tools act on the host the MCP server runs on,** which is the runner's: `execute_code_headless`, the `*_for_cli` tools and the file tools. They are not the operator's session, and are never on.

## Decision

- **A generic integration with a registry of vetted servers,** `artifactr.connect`: each entry, a `ConnectedServer`, names the app, how its server is started (its command and pinned version are the operator's configuration), how the app's host is passed to it, and **each tool it may offer with a risk**: `read`, `edit`, `code`, `network` or `host`. A tool the entry doesn't name is never offered, so a server that adds a tool in a new version adds nothing until the entry does. v1 vets **neka-nat's FreeCAD server** and **ahujasid's Blender server**. spkane's and Blender Lab's are documented here, not entries: the first for its size (each tool would need vetting), the second because every tool runs Python on the socket, so it has no `read` tier to offer (an owner's question, below).
- **Two integration keys per app,** declared in lattice-core's registry and off by default: `connect:<app>`, the app's `read` and `edit` tools, and `connect-code:<app>`, its `code` and `network` tools. A key is a family and one name ([lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md)), so the code key is a family of its own, not `connect:<app>:code`. The code key offers nothing unless the app's key is on too.
- **`host` tools are never offered,** whatever is switched: they run on the runner's machine, or read and write its files, and the native-files path is how a file enters lattice.
- **`code` and `network` tools are protected,** each of these, every call:
  1. **The operator enables each tool by name** (`allow=("execute_code",)`); a vetted entry's default never includes one.
  2. **The workspace's `connect-code:<app>` is on.**
  3. **The person the run acts for holds `artifactr:run_connected_code`,** a new action in artifactr's catalog. grantr gives it to a workspace's admins and a tenant's owners and admins, and to no editor; a custom role may hold it. A run acting for no one holds nothing. Checked when the tool is offered and again when it runs.
  4. **Every call waits for a person's approval,** on the deferred flow ([ADR-0083](0083-ask-user-asks-questions-with-options.md)). There is no "always allow": each call is its own request. The request's `args` carry the **full code**, so no approval is recorded for code that was not in it, and an approved call runs exactly those arguments: the runner passes approved or denied, never changed arguments. A request carries `review`, a new optional field of `DeferredRequest`: the app, that it runs code with the operator's own privileges in their own session, and the static findings.
  5. **The code is capped** (64 KiB) before it is offered for approval.
  6. **A static scan, advisory.** Before approval, the code is parsed and walked for imports of `os`, `subprocess`, `socket`, `ctypes`, `importlib`, `shutil`, `urllib`, `http`, `requests` and their kin, calls to `open`, `eval`, `exec`, `compile`, `__import__`, `getattr` with a computed name, dunder access (`__class__`, `__subclasses__`, `__globals__`, `__builtins__`), and `while True`. Each finding is shown to the approver. The deployment chooses `scan="warn"` (default: findings shown) or `scan="block"` (a finding refuses the call before it is offered, as a retry the model sees). **The scan is not a sandbox and cannot be made one:** Python reaches anything through the app's own modules (`FreeCAD`, `bpy`) and through tricks no deny-list catches, as ahujasid's own `safe_mode.py` says of its guard. **The approval is the gate;** the scan only helps the person read.
- **Results are untrusted data.** Each reply is capped (16,000 characters of text; an image of at most 2 MiB, else dropped with a note) and given to the model framed as the app's reply, data and not instructions. A tool's description, the server's words too, is cut at 1,000 characters. A server's `instructions` are never read; the client offers no sampling and no elicitation, so a server can't drive the model or ask a person anything.
- **Each call spawns the server on stdio, under a deadline** (30 seconds by default), as native files' crafting apps are; the tool list is read once and kept. The *app* keeps state, the server and lattice don't: unlike a native file's app, a port of stateless calls ([files ADR-0004](../files/adr/0004-an-app-is-a-port-of-stateless-calls.md)), **a connected app's state is the operator's own session**: what is open in it, what is selected, its undo history. lattice records what it asked and what came back, not the session.
- **The tools are named `<app>_<tool>`,** so `freecad_create_object` and `blender_get_scene_info` can't collide with each other or with artifactr's tools.
- **Loopback only.** The runner, the MCP server and the app run on one machine: the operator's own, or a host they trust. The server is given `127.0.0.1` (or `localhost`) as the app's host; another host is refused unless the operator passes `remote=True`, for a host on their own tailnet, which the [guide](../guides/connected-apps.md) describes. **A hosted portal can't reach a desktop's loopback,** and v1 does not bridge it: connected apps are for a local or self-hosted deployment, such as stackr's template on the operator's machine. A bridge an operator runs beside their app, dialing out to the portal, is a later decision.
- **Secrets are names, not values.** A token (`FREECAD_MCP_TOKEN`) is named in the configuration and read from the runner's environment as the server is spawned. It is passed only to the server, never into an artifact, a log line, an event or a span. The vetted Blender entry passes `DISABLE_TELEMETRY=true`.
- **Audit and trace.** The pause records each request with its full arguments and its review; the answer records who approved or denied it; `tool_called` and `tool_returned` record each call, their summaries redacted and truncated as every call's are ([ADR-0084](0084-what-a-run-records-of-its-calls-and-who-reads-it.md)).
- **What the app saves stays outside.** A `.FCStd` or `.blend` the operator saves is not an artifact; uploaded, it is a native file through the normal path, scanned, never trusted for having come from a connected app.
- **The kill switch is the workspace's switch.** `connect:<app>` off hides every tool of the app at the next model request; `connect-code:<app>` off hides the code tools, and refuses a call already approved but not yet run. Calls are paced by the run's own limits; no rate limit of its own.
- **portalr's approval card** shows a call with a `review` as a badge ("Runs code in your FreeCAD"), the code in a block of its own, copyable, and the findings, beside the full arguments it shows today.

## Options considered

| Option | For | Against |
|---|---|---|
| **A generic integration and a registry of vetted servers (chosen)** | One filter, one approval path, one test suite for every app; a new server is a declaration | A vetted entry must be kept up with its server |
| A bespoke integration per app | Each fits its server exactly | The protections written twice, and drift between them |
| Expose a server's whole tool list | Nothing to vet | A server's new `execute_*` is offered the day it ships |
| Code tools never offered | Simplest; nothing to approve | The owner asked for them, opt-in and protected |
| The scan as the gate | Fewer approvals | It can't be sound: Python reaches the OS through the app's modules |
| A long-lived server process per run | One spawn per run | State and a process lattice must supervise, against a stateful app it doesn't own |
| A bridge that lets a hosted portal reach a desktop | Hosted deployments can use it | A new service with an outbound tunnel and its own auth: a decision of its own |

## Consequences

- Easier: an operator who runs lattice beside their FreeCAD or Blender gives agents the app's own tools and a view of it, with nothing hostile entering through a file.
- Harder: every code call waits for a person, by design; the scan's findings help but are not a guarantee.
- Harder: the security of a connected app is the operator's machine's. Any local process can drive the app through its socket whether lattice is there or not; the guide says so first.
- Open, for the owner: whether Blender Lab's server becomes an entry (all of its tools are Python on the socket, and it needs Blender 5.1); whether `artifactr:run_connected_code` stays with admins or gets a dedicated role; and a bridge for hosted portals.
