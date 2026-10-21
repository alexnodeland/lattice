# Connected apps: your own FreeCAD or Blender

A connected app is a FreeCAD or Blender **you run yourself**, a desktop window or a headless instance you trust, that the agent drives through the app's community MCP server. It is off by default, and apart from native files: a FreeCAD or Blender file someone uploads still runs only in the worker, on its curated commands ([files ADR-0014](../files/adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md)). A connected app never opens a file for you; what it works on is what you opened in it ([ADR-0085](../adr/0085-connected-apps-an-operators-own-freecad-or-blender-through-a-vetted-mcp-server.md)).

## Read this first

The app's add-on listens on a port of your machine, `9875` for FreeCAD and `9876` for Blender, and runs Python sent to it. By default it asks no password. **Any process on your machine can drive the app through it, with your privileges, whether lattice is there or not.** lattice filters what the agent asks for; it can't change what the socket allows. Connect an app only on a machine you trust, set FreeCAD's token, and stop the add-on's server when you are done.

## What runs where

```
your machine (or a host you trust, on your tailnet)
  lattice's runner ──stdio──> the app's MCP server ──loopback──> the add-on, in your FreeCAD or Blender
```

The runner spawns the MCP server for each call, so all three run on one machine. A hosted portal can't reach your desktop's loopback: connected apps are for a local or self-hosted deployment, such as stackr's template on your machine.

## The vetted servers

| App | Server | Started as |
|---|---|---|
| FreeCAD | [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) (MIT) | `uvx freecad-mcp==<version>` |
| Blender | [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) (MIT) | `uvx blender-mcp==<version>`, with `DISABLE_TELEMETRY=true` |

Pin the version you have read. Each entry names every tool it may offer, with its risk; a tool it doesn't name is never offered.

| Risk | Offered when | Examples |
|---|---|---|
| `read` | `connect:<app>` is on | `freecad_get_objects`, `freecad_get_view`, `blender_get_scene_info` |
| `edit` | `connect:<app>` is on | `freecad_create_object`, `freecad_edit_object` |
| `code` | you allow the tool, `connect-code:<app>` is on, the person holds `artifactr:run_connected_code`, and someone approves **each call** | `freecad_execute_code`, `blender_execute_blender_code` |
| `network` | as `code` | `blender_search_assets`, `blender_import_asset` |
| `host` | never: it acts on the runner's machine or its files | `freecad_execute_code_headless`, `freecad_reload_document` |

## Connecting one

```python
from pydantic_ai import Agent, DeferredToolRequests

from artifactr.connect import FREECAD, Connection, connected_app_tools

freecad = Connection(
    FREECAD,
    command=("uvx", "freecad-mcp==0.1.27"),
    secrets=("FREECAD_MCP_TOKEN",),  # read from the runner's environment, passed only to the server
)
agent = Agent(
    model,
    toolsets=[connected_app_tools(freecad, integrations=grants)],
    output_type=[str, DeferredToolRequests],
)
```

Then switch `connect:freecad` on for the workspace in portalr's admin. The app's host is `127.0.0.1` unless you pass `host=`; another host is refused unless you pass `remote=True` too, for a machine on your own tailnet. Its add-on must then listen there, which is your choice to make in the app.

## Letting it run code

Running code is opt-in at every level, and every call waits for a person:

1. Allow each tool by name: `Connection(FREECAD, ..., allow=("execute_code",))`.
2. Switch `connect-code:freecad` on for the workspace.
3. Grant `artifactr:run_connected_code` to whoever may approve such runs: a workspace's admins hold it; give others a custom role.

The approval card shows "Runs code in your FreeCAD", the code itself, and what a quick scan found in it: imports such as `os`, `subprocess` or `socket`, calls such as `open`, `eval` or `exec`, dunder tricks, `while True`. **The scan is advisory**: Python reaches the operating system through FreeCAD's and Blender's own modules, in ways no list catches. Read the code; the approval is the gate. `Connection(..., scan="block")` refuses code with any finding before it reaches you. There is no "always allow".

## What comes back

Replies are data. Text is cut at 16,000 characters, an image (a view of the model) at 2 MiB, and the model is told the reply is the app's, not instructions. The server's own instructions are not read, and it can't ask the model or a person for anything.

A file you save in the app is yours. To share it, upload it as a native file: it is scanned like any other.

## Turning it off

Switch `connect:<app>` off and its tools are gone at the agent's next request; `connect-code:<app>` off refuses even a call already approved. Stop the add-on's server in the app to close the port.
