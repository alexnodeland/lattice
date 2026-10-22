# ADR-0085: Connected apps: an operator's own FreeCAD or Blender, through a vetted MCP server

**Status:** Proposed
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Beside:** native files' [ADR-0014](../files/adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md) (FreeCAD) and Blender's native files (in review, #445), which stay as they are

## Context

Native files run FreeCAD and Blender in the worker, on a curated script dialect, with no Python an agent or a file brings. That path is for files anyone may upload, hostile ones included. The owner asked for a second path, off by default: an **operator** connects a FreeCAD or Blender **they run themselves**, a desktop window or a trusted headless instance, through its community MCP server, so the agent gets the app's richer tools and a view of the part or scene. The owner added that the Python tools may be offered too, opt-in and protected.

### The servers

Read from their source on 2026-10-20; the two vetted ones were also listed, not run against an app, in a throwaway container, to pin their tools. Versions go stale: an entry names the one it vetted.

| Server | Licence, version, last push |
|---|---|
| [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) | MIT; `freecad-mcp` 0.1.27; 2026-10-13 |
| [spkane/freecad-addon-robust-mcp-server](https://github.com/spkane/freecad-addon-robust-mcp-server) | MIT; 2026-10-19 |
| [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) | MIT; `mcp-for-blender` 2.2.2; 2026-10-20 |
| [Blender Lab's blender_mcp](https://projects.blender.org/lab/blender_mcp) | GPL-3.0; 1.0.2; 2026-09-29; needs Blender 5.1 |

| Server | How it reaches the app | Authentication |
|---|---|---|
| neka-nat | an MCP server on stdio calls an add-on's XML-RPC server in FreeCAD's window, port 9875 | optional token (`FREECAD_MCP_TOKEN`); the add-on defaults to none, `allowed_ips=127.0.0.1`, `remote_enabled=false` (`addon/FreeCADMCP/rpc_server/settings.py`) |
| spkane | stdio or HTTP; XML-RPC on 9875, JSON-RPC on 9876, or FreeCAD inside the server's process | none found |
| ahujasid | stdio, to an add-on's socket in Blender, `localhost:9876` | none |
| Blender Lab | stdio, to an add-on's socket, `localhost:9876` | none |

| Server | Tools, by risk |
|---|---|
| neka-nat | read: `list_documents`, `get_objects`, `get_object`, `get_parts_list`, `get_view`, `get_rpc_status`, `get_async_status`; edit: `create_document`, `create_object`, `edit_object`, `delete_object`; code: `execute_code`, `execute_code_async`; on the runner's machine: `execute_code_headless` (a fresh FreeCAD where the server runs), `reload_document`, `insert_part_from_library` (its disk), `run_fem_analysis` (a solver) |
| spkane | 150+; code: `execute_python`, `safe_execute`, macro tools (Python kept on disk); files: `open_document`, `save_document`, `import_*`, `export_*`; leaks: `get_mcp_server_environment` |
| ahujasid | read: `get_scene_info`, `get_addon_status`, `look`; code: `execute_blender_code`; network: `search_assets`, `import_asset`, `generate_3d`; telemetry: `disable_telemetry`, `record_trajectory_feedback`. A minimal usage record is sent unless `DISABLE_TELEMETRY=true` |
| Blender Lab | every tool sends Python to the add-on (`tools_helpers/connection.py`), the reads as the server's own scripts; `*_for_cli` opens a `blend_file` in a background Blender on the server's machine; `render_*_to_path` writes files. Its page warns it "will execute LLM generated code in Blender without any guards" |

Three facts follow:

1. **The app's port runs Python for any local process.** Every add-on accepts code on its socket, and Blender's add-ons take no token. Whatever lattice filters governs only what the *agent* asks for, never what the socket allows. A connected app is as safe as the machine it runs on.
2. **A "read" tool is the server's code, run in the app.** Vetting a server is trusting its shipped scripts at one version.
3. **Some tools act on the machine the server runs on,** which is the runner's, not the operator's session.

## Decision

### What it is

- **A generic integration with a registry of vetted servers,** `artifactr.connect` (the `connect` extra, on the MCP SDK's client, `mcp>=2.2`, which artifactr's `files` extra already uses; not pydantic-ai's MCP client, which needs FastMCP). A `ConnectedServer` entry names its app, the release it vetted, the variable its add-on's token is read from, if it takes one, and **every tool it may offer**, each with a risk (`read`, `edit`, `code`, `network` or `host`) and a **digest**: the SHA-256 of the tool's name, description and input schema as the server lists them.
- **v1 vets neka-nat's FreeCAD server and ahujasid's Blender server.** FreeCAD's edits (`create_document`, `create_object`, `edit_object`) were audited in the add-on's source at v0.1.27: property values arrive as XML-RPC's plain values and are set with `setattr`, and none reaches `exec`, `eval`, `setExpression` or a `Proxy` the add-on builds, so they stay `edit`. spkane's is not an entry, for its size; Blender Lab's is not, because every tool runs Python on the socket, so it has no `read` tier to offer The owner decided it is not an entry in v0.2.
- **Two integration keys per app,** declared in lattice-core's registry and off by default: `connect:<app>`, its `read` and `edit` tools, and `connect-code:<app>`, its `code` and `network` tools, which offers nothing unless the app's key is on too. The owner suggested `connect:<app>:code`; lattice-core's registry takes a key of one name or two, one colon at most ([lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md)), so the code key is `connect-code:<app>`.

### Which tools, and when

- **A tool the entry doesn't name is never offered, nor one whose digest doesn't match.** A server that adds or changes a tool, its description included, changes nothing until the entry is vetted again; vetting it again is the re-approval. The tool list is read once a process and kept; since the server is a new process for each call, the call lists its tools in its own session and checks the one it calls against the digest before calling it. The registry pins the tools; the operator pins the install (below).
- **`host` tools are never offered,** whatever is switched: they act on the runner's machine or its files, or change what the server's maker collects (`disable_telemetry`, `record_trajectory_feedback`).
- **`code` and `network` tools are protected,** each of these, every call:
  1. **The operator allows each tool by name,** in the application's configuration (`Connection(allow=...)`). A workspace's admin can't widen it. A vetted entry never allows one. A per-tool switch in each workspace is a non-goal of v1: the workspace switches the app's code tools as one.
  2. **The add-on is authenticated:** the operator passes its token (`FREECAD_MCP_TOKEN`); for an add-on that takes none, as Blender's, they must say `unauthenticated=True`, and the guide says what that means.
  3. **The workspace's `connect-code:<app>` is on.**
  4. **The person the run acts for holds `artifactr:run_connected_code`,** a new action in artifactr's catalog, which grantr gives a workspace's admins and a tenant's owners and admins, and no editor; a custom role may hold it. The owner decided it stays with owners and admins: no dedicated role in v0.2. A run acting for no one, an unattended one, holds nothing.
  5. **Every call waits for a person's approval,** on the deferred flow ([ADR-0083](0083-ask-user-asks-questions-with-options.md)). There is no "always allow": each call is its own request, and its approval holds for 15 minutes by default (`approval_ttl`), as the owner decided, which the card says. The time runs from the ask to the call, the wait for another call to the same app included. The approval is kept with a digest of the arguments it was asked with, and a call with others runs nothing. The time is the run's pause, as the workspace's log keeps it (the `run_paused` event's time, and the arguments it asked with), so an approval holds across a restart and in another runner process alike, and one past its time, or of other arguments, is refused and asked again (since 2026-10-22; v0.2 first kept it in the process, failing closed). A runner that dies after the call ran but before its `tool_returned` may run it again on resume: the app's state is the operator's, and nothing replays it. An answer resumes the run *for whoever gave it*, and the call is checked again before it runs, so **the approver must hold the action** too; one who doesn't runs nothing. The approval is bound to the request's tool call: the runner passes approved or denied, never changed arguments, so **what runs is byte for byte what was shown.**
  6. **The request carries the full code,** in `args` and again in `review`, a new optional field of `DeferredRequest`, beside the app, what running it means ("runs code in your FreeCAD, in the session you have open, with your own privileges: it can do anything you can"), and the scan's findings. Code that is missing, blank or over 64 KiB is never offered for approval.
  7. **Calls to one app run one at a time,** reads, edits and the listing of its tools too, since they share the operator's one session. The lock is an `AppLock`, by the app's server and address: by default the runner process's (`ProcessLock`), on its one event loop; with more than one runner process, on PostgreSQL, the application passes `artifactr.sql.AdvisoryLock(engine)`, a session-level `pg_advisory_lock` held on a connection of its own for the call, which a process that dies lets go of with its connection. Any other database has no such lock, and is run with one runner process.
8. **Each workspace runs so many code and network calls an hour,** 30 by default (`Connection(per_hour=...)`, a number or the application's answer for each tenant and workspace, such as a setting its admins change). Each call that runs records an `app_event`, `artifactr.connect.called`, in the workspace's log, and the hour's are counted there, before the call is offered for approval and again before it runs, so every runner process counts the same calls. The approval card says which of the hour's calls it is ("Call 3 of 30 this workspace may run this hour."), and a call past the limit is refused, saying so. Two processes counting at once may each run one call past it.
- **The scan is advisory.** Before approval, the code of each `code` tool (the argument the entry names) is parsed and walked for imports of modules with the process, files or network in them (`os`, `subprocess`, `socket`, `ctypes`, `importlib`, `shutil`, `urllib`, `requests` and their kin), calls to `open`, `eval`, `exec`, `compile`, `__import__`, `getattr` with a computed name, dunders that climb out of an object, `while True`, and characters a reader doesn't see (controls, separators, soft hyphens, zero-width, direction-changing and tag characters, variation selectors, lone surrogates); code that doesn't parse, or is too deep to analyse, is a finding too. The card shows each unseen character as its code point, in the code and in the call's arguments, says when the scan found nothing that it can't find everything, and says when the code is longer than what it shows before it is unfolded. The deployment chooses `scan="warn"` (the default, findings shown) or `scan="block"` (a finding refuses the call before anyone is asked, as a retry the model sees, which also tells it what to avoid). **It is not a sandbox and cannot be one.** It misses an alias (`import os as o` is found, `o = __builtins__` then anything is not), a module the app already imported, code built as a string and handed to the app's own evaluators, `getattr` with a constant name, and the app's own modules, which open files and reach the system (`bpy.ops.wm`, `FreeCAD.loadFile`, `Mesh.open`), as ahujasid's own `safe_mode.py` says of its guard. `block` mode's message tells the model what to avoid, which helps it evade the scan too. **The approval is the gate.**
- **Network tools** (`search_assets`, `import_asset`, `generate_3d`) are protected the same way, with their own badge, "Downloads from the internet into your Blender", and the card says where the call reaches: each network tool's entry names the argument that picks the service (`source`, `provider`) and the hosts each of its values reaches, read in the server's source at its release (Poly Haven's, Sketchfab's and Poly Pizza's; Hyper3D Rodin's, Hunyuan3D's and Meshy's). A value the entry doesn't name is shown as unvetted. What they fetch, a `.blend` among them, is the untrusted-file case, opened in a live, privileged app rather than the worker: the approver is told so.

### The server process

- **It is third-party code, run unsandboxed as the runner's user,** for each call, in its own process group, in an empty temporary directory that is also its `HOME` (on Linux and macOS), under a deadline (30 seconds), and the group is ended with the call. Its environment is the MCP SDK's minimal one (`PATH`, `USER`, `SHELL`, `TERM`, `LOGNAME`), the entry's own variables (Blender's `DISABLE_TELEMETRY=true`) and the secrets the operator names: the runner's model keys and everything else stay out. What it prints to stderr goes nowhere. Its network and file system are the runner's: **none of this contains a hostile server;** it keeps an honest one from what it doesn't need.
- **A named token must be set,** or the server isn't started: the operator's configuration can't claim a token the environment doesn't hold.
- **It is installed ahead by the operator,** at the entry's version, so no call downloads it; the guide recommends a locked requirement with hashes. **lattice doesn't verify the install:** it refuses a server whose `initialize` reports another version than the one recorded when it was vetted, which catches an accident, not a forgery (FreeCAD's server reports none; Blender's reports 1.30.0, not its release); the digests then check every tool the agent may call.
- **The deadline ends the server, not code running in the app:** a loop the agent wrote keeps FreeCAD's or Blender's window busy until the operator stops it. `execute_code_async` starts a job in the app that outlives its call; the switches and the deadline don't reach it.
- **No sampling, no elicitation, no roots.** The client declares none, and the SDK answers each such request with an error, so a server can't drive the model or ask a person anything. A server's `instructions` are never read.

### What comes back

- **Results are untrusted data.** At most 32 parts of a reply are read; its text is capped at 16,000 characters before it is joined, stripped of terminal escapes, controls but tabs and newlines, and zero-width and direction-changing characters, and given to the model between marks with a nonce of the reply's own, which the server can't write, with a sentence that says it is the app's and no instruction. A refusal is framed the same way. An image is given only if it starts like the PNG or JPEG it says it is, its base64 is at most 2 MiB's worth before it is decoded, all of a reply's images together too, and its header (a PNG's `IHDR`, a JPEG's frame) says it is at most 8,000 pixels a side (`IMAGE_SIDE`): a larger one is left out with a note that gives its size and the limit, and is never scaled; one whose size can't be read is left out too. No error the server causes reaches the model in its words: lattice says it ended, or answered with what isn't MCP. A tool's description, the server's words too, is cut at 1,000 characters. **None of this neutralises a prompt injection;** it only marks where the app's words are, and the approval of every protected call is what holds.
- **What the app saves stays outside.** No artifact takes a path or a file from the app's output. A `.FCStd` or `.blend` the operator saves and uploads is a native file through the normal path, scanned, never trusted for having come from a connected app.

### Where it runs

- **Loopback by default.** The server is given `127.0.0.1` (or `::1`) as the app's host, an address, not `localhost`; anything else, `0.0.0.0` and `::` among them, is refused unless the operator passes `remote=True`, and then only a tailnet's address (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`) or a `.ts.net` name of lowercase ASCII labels and nothing else, with the add-on's token, since the add-on's RPC is plain text: the tailnet encrypts and authenticates it, the token says it is lattice. Both vetted servers take `--host` from their command line before their environment (read in their source); Blender's takes `--port` too, FreeCAD's port is fixed at 9875, and a port given to it is refused. An add-on with no token allowed to run code logs a warning. Blender's add-on takes no token, so a remote Blender is refused. The guide never asks anyone to open the add-on's port beyond loopback or a tailnet.
- **Two deployments work:** the runner on the operator's own machine, beside the app (stackr's template run locally); or a self-hosted runner on a host of the operator's tailnet, reaching a FreeCAD whose add-on listens on its tailnet address, with its token. **A hosted portal can't reach a desktop's loopback,** and, as the owner decided, v0.2 builds no bridge for it.
- **One operator's host.** A host other people log into can reach the add-on's port; that is out of scope, and the guide says so.

### Records

- **Secrets are names, not values:** read from the runner's environment as the server is spawned, passed to nothing else, never into an artifact, a log line, an event, a span or a review.
- **The pause records each request with its full arguments and its review,** the code as the agent wrote it, unredacted, since what is approved must be what runs; the answer records who approved or denied it; `tool_called` and `tool_returned` record each call, their summaries redacted and truncated as every call's are ([ADR-0084](0084-what-a-run-records-of-its-calls-and-who-reads-it.md)).
- **The kill switch is the workspace's:** `connect:<app>` off hides every tool of the app at the next model request, and refuses a call in flight; `connect-code:<app>` off hides the code tools, so a call approved but not yet run isn't run.
- **The operator sees each failure** in the runner's log, as a warning in lattice's words, with nothing the server printed and so no secret.

### Where each part lands

| Part | Where |
|---|---|
| The keys | lattice-core's `KNOWN`; portalr's admin lists them unchanged |
| `artifactr:run_connected_code` | artifactr's action catalog; grantr's built-in roles take it as a workspace admin's |
| The registry, connection, scan and toolset | `artifactr.connect`, the `connect` extra |
| `DeferredRequest.review` | artifactr's protocol, its JSON Schema and portalr's generated types |
| The approval card's badge, code and findings | portalr's chat |

## Plan

1. The registry and `connect:<app>`'s read and edit tools, on loopback.
2. `connect-code:<app>`: the action, the approval with its review, the scan, portalr's card.
3. The tools pinned by digest, at listing and at each call.
4. Later: a bridge for hosted portals; a per-tool workspace switch if wanted.

Stages 1 to 3 land together, in one pull request after this one.

### Conformance

Proven by tests against a fake server on stdio:

- no code tool is offered by default, nor without the operator's `allow`, the code key, the person's action, or the add-on's token or `unauthenticated`;
- a tool no entry names, and a `host` tool, is never offered;
- a tool whose digest changed is left out, and one that changed between the listing and the call isn't run;
- a person without the action, at the call, runs nothing; so does an approver without it;
- every protected call pauses, with no "always allow", and what runs is byte for byte the approved arguments; an approval past its time runs nothing; an approval holds across a restart, since its time is the logged pause's;
- a workspace past its hourly limit is asked nothing and runs nothing, and calls over an hour ago don't count;
- calls take turns by the lock the connection is given; PostgreSQL's advisory lock makes two engines take turns; a database without one is refused;
- an image past 8,000 pixels a side, PNG or JPEG, is left out saying its size and the limit;
- a network call's card says where it reaches;
- calls to one app don't overlap;
- a named token that isn't set starts nothing; a server that reports another version offers nothing, and a failed listing isn't asked again for 30 seconds;
- the server sees only the minimal environment and its named secrets, with its temporary directory as `HOME`; what it prints never reaches the model; the deadline ends its process;
- code with an unseen character, a NUL, nesting too deep to parse, or a lone surrogate is a finding or refused;
- grantr's real roles over artifactr's real catalog: only owners and admins hold the action;
- the vetted digests match the tool lists recorded from the servers when they were vetted;
- code missing, blank or over 64 KiB is never offered; findings show; `block` refuses before anyone is asked;
- an oversized reply and an oversized or mislabelled image are capped or left out; an injection stays inside the frame; a slow call ends at the deadline; a server that isn't MCP, or isn't there, offers nothing;
- a host other than loopback is refused without `remote=True`, and remote without the token;
- a secret not named isn't passed; a server's sampling and elicitation are refused; its instructions never reach the model;
- the kill switch hides the tools and refuses a call already approved; two toolsets of one app collide loudly, and two apps don't, by their prefixes.

Not proven: the vetted servers were read and listed, never run against FreeCAD or Blender; the install is the operator's, unverified beyond the reported version and the digests; whether an add-on enforces its token is the add-on's; the scan is advisory by design; that a secret never reaches a span is held by passing it only to the server, not by a test of every exporter; a hostile server process is not contained.

## Options considered

| Option | For | Against |
|---|---|---|
| **A generic integration and a registry of vetted, pinned servers (chosen)** | One filter, one approval path, one test suite for every app; a new server is a declaration | An entry must be vetted again for each release |
| A bespoke integration per app | Each fits its server exactly | The protections written twice, and drift between them |
| Expose a server's whole tool list | Nothing to vet | A server's new `execute_*` is offered the day it ships |
| Pin the version only | Simpler | A republished release or a changed description goes unseen |
| Code tools never offered | Simplest | The owner asked for them, opt-in and protected |
| The scan as the gate | Fewer approvals | It can't be sound |
| A long-lived server process per run | One spawn per run | A process lattice must supervise, against a stateful app it doesn't own |
| A bridge so a hosted portal reaches a desktop | Hosted deployments can use it | A new service with an outbound tunnel and its own auth |

## Consequences

- Easier: an operator who runs lattice beside their FreeCAD or Blender gives agents the app's own tools and a view of it, with nothing hostile entering through a file.
- Harder: every code call waits for a person, by design.
- Harder: a connected app's security is its machine's; any local process can drive the app through its socket whether lattice is there or not.
- Harder: a connected app's state is the operator's own session, unlike a native file's app, a port of stateless calls ([files ADR-0004](../files/adr/0004-an-app-is-a-port-of-stateless-calls.md)): nothing can be replayed, so an edit or code call that fails mid-way is never retried automatically; the agent is told, and the operator sees the app as it is.
- Harder: each release of a vetted server is a new vetting, its digests computed again.
- Decided by the owner, above: Blender Lab's server is not a v0.2 entry; `artifactr:run_connected_code` is held by owners and admins only; an approval holds 15 minutes; no bridge for hosted portals in v0.2.
- Since 2026-10-22, as the owner decided: a lock shared between runner processes on PostgreSQL; a per-workspace hourly limit on code and network calls, counted in the log; images past 8,000 pixels a side refused, saying so; an approval's time kept with the run, so it survives a restart.
- Follow-ups: a per-tool switch in each workspace (undecided); portalr's admin setting for the hourly limit, which `per_hour` takes.
