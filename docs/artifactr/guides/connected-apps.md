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

Then switch `connect:freecad` on for the workspace in portalr's admin. The server's environment is only `PATH`, `USER` and the like, the entry's variables and the secrets you name: your model keys stay out. A token you name must be set, or the server isn't started. It runs in an empty temporary directory, its `HOME` too on Linux and macOS, for at most 30 seconds a call, and what it prints goes nowhere: a failure is logged as a warning in lattice's words; to debug the server, run it yourself. None of this contains a hostile server.

The host is an address: `127.0.0.1` or `::1`, not `localhost`. With `remote=True` it is your tailnet's: prefer its address (`100.x.y.z` or `fd7a:115c:a1e0::…`). A `.ts.net` name is accepted as a name, without checking where it resolves: a Funnel name resolves publicly, and the tailnet encrypts the add-on's RPC only when the runner is on the tailnet too. FreeCAD's token is required; a remote Blender is refused, since its add-on takes no token.

## Letting it run code

Running code is opt-in at every level, and every call waits for a person:

1. Allow each tool by name, with the add-on's token: `Connection(FREECAD, ..., secrets=("FREECAD_MCP_TOKEN",), allow=("execute_code",))`. Blender's add-on takes no token, so its code and network tools need `unauthenticated=True` too: you accept that any process on your machine can do the same.
2. Switch `connect-code:freecad` on for the workspace.
3. Grant `artifactr:run_connected_code` to whoever may run such code and approve it: a workspace's admins hold it; give others a custom role.

The approval card shows "Runs code in your FreeCAD", what that means, the code itself to read and copy, and what a quick scan found in it: imports such as `os`, `subprocess` or `socket`, calls such as `open`, `eval` or `exec`, dunder tricks, `while True`, code that doesn't parse. **The scan is advisory**: Python reaches the operating system through FreeCAD's and Blender's own modules, in ways no list catches. Read the code; the approval is the gate. `Connection(..., scan="block")` refuses code with any finding before anyone is asked. There is no "always allow", and what runs is exactly what you approved. An approval holds for 15 minutes (`approval_ttl`), counted from the run's pause in the workspace's log to the call, for the arguments it was asked with, so it holds across a restart and in another runner process too. Only owners and admins hold `artifactr:run_connected_code`. A character you wouldn't see is shown as its code point; long code says so above its fold. Calls to one app run one at a time: in the runner's process by default; with more than one runner process, on PostgreSQL, pass `lock=AdvisoryLock(engine)` (from `artifactr.sql`), on an engine of its own, with a pool as large as the calls a process may make at once, which every process on that database takes turns by. A call waits for its turn at most its deadline. On any other database, run one runner process. Each workspace runs at most 30 code and network calls to each app an hour (`per_hour`: a number, or, wired by your application, which nothing does for you, `Connection(FREECAD, command=..., per_hour=per_hour_setting(grants, "freecad"))` to read the `connect-per-hour:freecad` setting, which tenant and workspace admins may only lower from the operator's value in grantr's `operator_settings`, read each call, 0 if it can't be read), exactly, however many are asked at once; the card says how many of the hour's have run, and a call past the limit is refused, saying so. An approval is for one try: a call that was tried, whether it ran or failed, is asked again. A download's card says where it reaches: the library or generator it names, its hosts, and an image address the model gave; a service that wasn't vetted is refused. FreeCAD's edits never set a property named with `_`, `ExpressionEngine` or `Proxy`, and take their properties only as an object.

A download (`blender_import_asset`) shows "Downloads from the internet into your Blender": what it fetches is as untrusted as any uploaded file, and it opens in your live app.

The 30 seconds end the server, not the code: a loop the agent wrote keeps your app busy until you stop it, and `freecad_execute_code_async` starts a job that outlives its call.

## What comes back

Replies are data. Text is cut at 16,000 characters and stripped of terminal escapes and controls, and an image, a view of the part or scene, is given only if it starts like the PNG or JPEG it says it is, up to 2 MiB, 8,000 pixels a side and 16 million pixels (a larger one is left out, with a note that says its size and the limit; nothing is scaled); refusals are framed the same way. The model is told the reply is the app's, not instructions, which marks where the app's words are but doesn't stop a prompt injection: the approval of every code call does. The server's own instructions are not read, and it can't ask the model or a person anything.

A file you save in the app is yours. To share it, upload it as a native file: it is scanned like any other.

## Turning it off

Switch `connect:<app>` off and its tools are gone at the agent's next request; `connect-code:<app>` off means even a call already approved isn't run. Stop the add-on's server in the app to close the port.
