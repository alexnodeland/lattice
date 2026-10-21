# Connected apps: your own FreeCAD or Blender

A connected app is a FreeCAD or Blender **you run yourself**, a desktop window or a headless instance you trust, that the agent drives through the app's community MCP server. It is off by default, and apart from native files: a FreeCAD or Blender file someone uploads still runs only in the worker, on its curated commands ([files ADR-0014](../files/adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md)). A connected app never opens a file for you; what it works on is what you opened in it ([ADR-0085](../adr/0085-connected-apps-an-operators-own-freecad-or-blender-through-a-vetted-mcp-server.md)).

## Read this first

- **The app's add-on runs Python for any process on your machine.** It listens on a port, `9875` for FreeCAD and `9876` for Blender. FreeCAD's takes a token if you set one; Blender's takes none. Any process on your machine can drive the app through it, with your privileges, whether lattice is there or not. lattice filters what the agent asks for; it can't change what the socket allows.
- **The app's MCP server is third-party code,** run as the runner's user, unsandboxed, for each call.
- **Connect an app only on a machine that is yours alone.** A machine other people log into can reach the add-on's port too.
- **Never open the add-on's port to a network** beyond loopback, or your own tailnet with FreeCAD's token set. Stop the add-on's server when you are done.

## What runs where

```
your machine
  lattice's runner ──stdio──> the app's MCP server ──loopback──> the add-on, in your FreeCAD or Blender
```

The runner starts the MCP server for each call, so they run on one machine: yours, with stackr's template run locally. Or the runner runs on a host of your own tailnet and reaches a FreeCAD that listens on its tailnet address, with its token: `remote=True`. A hosted portal can't reach your desktop's loopback, and nothing bridges it yet.

## The vetted servers

| App | Server | Vetted release | Token |
|---|---|---|---|
| FreeCAD | [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) (MIT) | `freecad-mcp==0.1.27` | `FREECAD_MCP_TOKEN` |
| Blender | [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) (MIT) | `mcp-for-blender==2.2.2`, with `DISABLE_TELEMETRY=true` | none |

Each entry names every tool it may offer, with its risk and a digest of what the server says the tool is. A tool the entry doesn't name, or one whose name, description or schema changed, is never offered or run: a new release needs a new entry.

| Risk | Offered when | Examples |
|---|---|---|
| `read` | `connect:<app>` is on | `freecad_get_objects`, `freecad_get_view`, `blender_get_scene_info` |
| `edit` | `connect:<app>` is on | `freecad_create_object`, `freecad_edit_object` |
| `code` | you allow the tool, `connect-code:<app>` is on, the person holds `artifactr:run_connected_code`, and someone who holds it approves **each call** | `freecad_execute_code`, `blender_execute_blender_code` |
| `network` | as `code` | `blender_search_assets`, `blender_import_asset` |
| `host` | never: it acts on the runner's machine or its files, or on telemetry | `freecad_execute_code_headless`, `freecad_reload_document`, `blender_disable_telemetry` |

## Installing the server

Install it ahead, at the vetted release, so no call downloads anything. lattice doesn't verify what you installed: it checks the version the server reports and the digest of every tool it calls. A locked requirement with hashes, in a directory of its own, is the way to get the release you mean:

```sh
uv venv /opt/connected/freecad
echo "freecad-mcp==0.1.27" > /opt/connected/freecad.in
uv pip compile --generate-hashes /opt/connected/freecad.in -o /opt/connected/freecad.txt
uv pip install --python /opt/connected/freecad --require-hashes -r /opt/connected/freecad.txt
```

## Connecting one

```python
from pydantic_ai import Agent, DeferredToolRequests

from artifactr.connect import FREECAD, Connection, connected_app_tools

freecad = Connection(
    FREECAD,
    command=("/opt/connected/freecad/bin/freecad-mcp",),
    secrets=("FREECAD_MCP_TOKEN",),  # read from the runner's environment, passed only to the server
)
agent = Agent(
    model,
    toolsets=[connected_app_tools(freecad, integrations=grants)],
    output_type=[str, DeferredToolRequests],
)
```

Then switch `connect:freecad` on for the workspace in portalr's admin. The server's environment is only `PATH`, `USER` and the like, the entry's variables and the secrets you name: your model keys stay out. A token you name must be set, or the server isn't started. It runs in an empty temporary directory, its `HOME` too, for at most 30 seconds a call, and what it prints goes nowhere: to debug it, run it yourself. None of this contains a hostile server.

The host is an address: `127.0.0.1` or `::1`, not `localhost`. With `remote=True` it is your tailnet's (`100.x.y.z`, `fd7a:115c:a1e0::…` or a `.ts.net` name), and FreeCAD's token is required; a remote Blender is refused, since its add-on takes no token.

## Letting it run code

Running code is opt-in at every level, and every call waits for a person:

1. Allow each tool by name, with the add-on's token: `Connection(FREECAD, ..., secrets=("FREECAD_MCP_TOKEN",), allow=("execute_code",))`. Blender's add-on takes no token, so its code and network tools need `unauthenticated=True` too: you accept that any process on your machine can do the same.
2. Switch `connect-code:freecad` on for the workspace.
3. Grant `artifactr:run_connected_code` to whoever may run such code and approve it: a workspace's admins hold it; give others a custom role.

The approval card shows "Runs code in your FreeCAD", what that means, the code itself to read and copy, and what a quick scan found in it: imports such as `os`, `subprocess` or `socket`, calls such as `open`, `eval` or `exec`, dunder tricks, `while True`, code that doesn't parse. **The scan is advisory**: Python reaches the operating system through FreeCAD's and Blender's own modules, in ways no list catches. Read the code; the approval is the gate. `Connection(..., scan="block")` refuses code with any finding before anyone is asked. There is no "always allow", and what runs is exactly what you approved. An approval holds for 15 minutes (`approval_ttl`), and only in the process that asked: after a restart, the agent asks again. A character you wouldn't see is shown as its code point; long code says so above its fold. Calls to one app run one at a time.

A download (`blender_import_asset`) shows "Downloads from the internet into your Blender": what it fetches is as untrusted as any uploaded file, and it opens in your live app.

The 30 seconds end the server, not the code: a loop the agent wrote keeps your app busy until you stop it, and `freecad_execute_code_async` starts a job that outlives its call.

## What comes back

Replies are data. Text is cut at 16,000 characters and stripped of terminal escapes and controls, and an image, a view of the part or scene, is given only if it starts like the PNG or JPEG it says it is, up to 2 MiB; refusals are framed the same way. The model is told the reply is the app's, not instructions, which marks where the app's words are but doesn't stop a prompt injection: the approval of every code call does. The server's own instructions are not read, and it can't ask the model or a person anything.

A file you save in the app is yours. To share it, upload it as a native file: it is scanned like any other.

## Turning it off

Switch `connect:<app>` off and its tools are gone at the agent's next request; `connect-code:<app>` off means even a call already approved isn't run. Stop the add-on's server in the app to close the port.
