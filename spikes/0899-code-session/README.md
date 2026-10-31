# Spike #899: one code session end to end, before the ports RFC

**Throwaway.** Nothing in this folder is imported, tested or shipped. It is here so the
ports RFC ([#893](https://github.com/alexnodeland/lattice/issues/893)) can answer it point by
point, and it is deleted once the RFC is accepted. Spike code is not to be copied into a
package's `src/`.

Run on 2026-10-30, on macOS (Apple silicon) with Docker Desktop, time-boxed to one sitting.
Versions: opencode 1.19.5, `@agentclientprotocol/claude-agent-acp` 0.99.1, Forgejo 11,
gVisor `release-20261026.0` (aarch64), OpenSandbox server and SDK 1.2.0, LiteLLM as installed
on the host.

## What was built

```
lattice (host)  ── opencode serve's API ─────────────┐
   │            ── ACP over `docker exec -i` stdio ──┤
   │                                                 ▼
   │            sandbox (internal network only: no internet, no forge, no host)
   │              ├─ the clone, remote = http://proxy:8080/<owner>/<repo>.git, no credential
   │              └─ opencode / claude-agent-acp, baseURL = http://proxy:8081/v1, dummy key
   │                         │
   │            proxy (on both networks), outside the sandbox
   │              ├─ :8080 credential proxy ─ adds the forge token ──▶ Forgejo
   │              └─ :8081 egress proxy ─ adds the LiteLLM key ─────▶ LiteLLM ─▶ stub model
   └─ Forgejo API (server side): open the pull request, read the commit status
```

| File | What it is |
|---|---|
| [`proxies.py`](proxies.py) | The credential proxy (git smart-HTTP, reads `receive-pack`'s ref updates) and the egress proxy (adds the model key) |
| [`stub_model.py`](stub_model.py) | A scripted OpenAI-compatible model: `write` a file, then `bash ls` (an `ask`), then a final answer |
| [`litellm.yaml`](litellm.yaml) | The throwaway LiteLLM config, two routes to the stub |
| [`opencode.json`](opencode.json) | The per-session opencode config lattice would generate |
| [`drive_opencode.py`](drive_opencode.py) | Lattice's side of an opencode session, over `opencode serve` |
| [`drive_acp.py`](drive_acp.py) | Lattice's side of an ACP agent, over the sandbox's exec stream |
| [`opensandbox.toml`](opensandbox.toml) | OpenSandbox's server config, Docker runtime with gVisor |
| [`Dockerfile.sandbox`](Dockerfile.sandbox) | The sandbox image |

## What worked

- **One task end to end on Forgejo with opencode**: clone through the credential proxy, opencode
  writes a file and asks before `ls`, the ask is answered over the API, lattice runs `git diff`,
  commits and pushes `lattice/s1`, opens the pull request through Forgejo's API (draft by its
  `WIP:` title prefix), and reads the combined commit status back (`success`, from a status
  posted by hand, see [Stubbed](#what-was-stubbed-and-why)).
- **The sandbox never saw a token.** Its environment and `.git/config` hold none. From inside
  it, the forge, the host, LiteLLM and the internet are unreachable; through the proxy, the
  forge's API (`/api/v1/user`), any other repository and LiteLLM's admin paths (`/key/info`) get
  403. Only git for the one repository and LiteLLM's `/v1/*` pass.
- **Push policy read from git's protocol**, for names: the ref-update commands before the pack
  are four lines of pkt-line, and the proxy refused a push to `main`, a tag and a deletion of the
  session's branch, and allowed the session's branch.
- **The model routed through LiteLLM** with the key added outside the sandbox, for both agents.
  opencode's `@ai-sdk/openai-compatible` provider worked with no network to npm: 1.19.5 bundles
  it.
- **gVisor runs on this machine**, inside Docker-in-Docker (a privileged `docker:dind` with
  `runsc` added as a runtime), not in Docker Desktop's own daemon, which was left alone. A whole
  opencode session ran under `runsc` (kernel `4.19.0-gvisor`): clone, edit, permission ask, idle,
  file-watcher events. inotify works.
- **OpenSandbox on gVisor**: its server, pointed at that daemon with `secure_runtime.type =
  "gvisor"`, checked that `runsc` exists at start-up, created a sandbox from the spike's image in
  about 1 s, with `runtime=runsc`, its capability drops, and its `execd` answering inside.
- **One ACP agent over stdio**: Claude Code through `claude-agent-acp`, launched with
  `docker exec -i` in the same sandbox, model at LiteLLM through the egress proxy. `initialize`,
  `session/new`, `session/prompt`, one `session/request_permission` (answered `allow_once`) and
  `end_turn`, in 3 s.

## What didn't

- **Force-pushes were not refused.** `git push -f origin HEAD~1:lattice/s1` passed: the
  ref-update line says `old new ref`, and nothing in it says whether `new` descends from `old`.
  The proxy needs ancestry, which it can get only by reading the pack against the current tip (a
  bare mirror per session, updated by the proxy, with `git merge-base --is-ancestor` in a
  quarantine), or by asking the forge afterwards, which is too late. The forge's own branch
  protection (no force-push on `lattice/*`) is the cheap second line where the forge has it.
- **Refusals read badly in git.** A 403 on `git-receive-pack` gives "the remote end hung up
  unexpectedly" or even "Everything up-to-date". The proxy should answer with a `report-status`
  (`ng <ref> <reason>`) so the agent and the person see why.
- **opencode's `/session/{id}/diff` returned `[]`** while `SPIKE.md` existed (untracked). The
  diff lattice shows must be its own `git diff`, as #893's principle already says.
- **The permission endpoint #884 and #888 name is deprecated.** In 1.19.5,
  `POST /session/{id}/permissions/{permissionID}` is `deprecated: true`; the spike answered with
  `POST /permission/{requestID}/reply` (`{"reply": "once"}`). There is also a second, newer
  surface under `/api/session/...` (`prompt` with `delivery: steer | queue`, `PermissionV2Reply`,
  `question` replies), and three event streams (`/event`, `/global/event`, `/api/event`).
- **opencode's event stream is noisy, and polling was what worked.** One short turn sent 105
  events: 45 `plugin.added`, 18 `message.part.updated`, 13 `message.updated`, 8 `session.status`.
  The driver found the ask and the end of the turn by polling `/permission` and
  `/session/status` every 250 ms, not by parsing the stream.
- **Claude Code's model wiring needed two workarounds in LiteLLM.** On an `openai/` route,
  LiteLLM turned Anthropic Messages into the Responses API (`/v1/responses`), which the backend
  didn't serve; on a chat-completions route (`hosted_vllm/`) it needed `drop_params: true`
  (Claude Code sends `context_management`). The egress proxy also had to strip `x-api-key`, not
  only `Authorization`.
- **ACP's `fs/*` methods were never called.** The spike offered `readTextFile` and
  `writeTextFile`; Claude Code wrote `SPIKE.md` to disk itself. So the working tree, not the ACP
  client, is the source of truth for edits, and "ACP's file-system methods are served from the
  sandbox" (#895) is unproven and may be unnecessary.
- **Exec through OpenSandbox is unproven here**, because of the test rig: its server ran on the
  Mac and couldn't reach the ports the inner daemon published, so the SDK's health check timed
  out. Not an OpenSandbox defect; it needs a Linux host to test.
- **gVisor's install has traps**: its `latest` download URLs return 404 (pin a GitHub release);
  the tarball's `gvisor-bin/` sidecars must sit beside `runsc` (else `gvisor_sentry` is not
  found); and `runsc` doesn't emulate other architectures, so an amd64 image fails with
  `exec format error`, where runc under Docker Desktop silently emulated it.

## Timings

Measured once each; nested in Docker-in-Docker inside Docker Desktop's VM, so they show orders of
magnitude, not what a Linux host will do.

| Step | Time |
|---|---|
| Forgejo container to healthy | 9 s |
| Sandbox image build: arm64 native / amd64 emulated | 58 s / 579 s |
| Image size: arm64 / amd64 | 614 MB / 774 MB |
| `docker save \| docker load` into the inner daemon: arm64 / amd64 | 70 s / 277 s |
| Container start (`true`): runc / runsc | 0.20 s / 0.19 s |
| `opencode --version`: runc / runsc | 0.50 s / 0.57 s |
| Clone through the credential proxy: runc / runsc | 0.58 s / 0.36 s |
| `opencode serve` to listening | 4 s (amd64, emulated) |
| opencode turn (write, ask, `ls`, answer) to idle, arm64 under runsc | 1.8 s |
| The same turn, amd64 under emulation on runc | 8.5 s (emulation; don't compare with the line above) |
| Claude Code over ACP, `initialize` to `end_turn` | 3 s |
| Push of the branch through the proxy | 1.9 s |
| Open the pull request and read the status | under 3 s |
| OpenSandbox: create a sandbox (image already local) | about 1 s |

## What was stubbed and why

- **The model**: a scripted stub ([`stub_model.py`](stub_model.py)) behind LiteLLM, because no
  model key was available without reading secrets. It proves the routing, the key injection and
  the tool loop, not the agents' quality or real streaming lengths.
- **CI**: the check was a commit status posted through Forgejo's API, because there was no
  Actions runner. The read-back path (`GET /commits/{sha}/status`) is real.
- **GitHub**: not run. It needs a GitHub App or token, which the spike couldn't hold without
  reading secrets; it is the half of #899's first criterion that remains.
- **The egress proxy** is a reverse proxy with fixed upstreams, not a forward proxy with an
  allowlist. That was enough here because both agents take a base URL; package registries would
  need a forward proxy.
- **Policy translation**: `opencode.json`'s `bash: ask` was exercised; `git push*: deny`,
  `webfetch`, `doom_loop` and Claude Code's `settings.json` permissions were not.

## What the ports RFC (#893) should take from it

### Sandbox port

- `create(image, resources, network_policy, labels) → Sandbox`, `exec(cmd, stdin?, stream) →
  Process` (a duplex stream, because ACP runs over it), `read`/`write` files, `expose(port) →
  url`, `pause`, `resume`, `snapshot`, `destroy`, `status`.
- **Capabilities**, so an adapter can delegate to what its backend already has: OpenSandbox 1.2
  has `networkPolicy` (ordered egress rules and a default action, enforced by an egress sidecar
  in `dns` or `dns+nft` mode, chainable to an upstream proxy), a `credential-vault` (credentials
  bound by host, path and method, injected as bearer, basic, API-key or custom headers by a MITM
  proxy, write-only and revisioned), pools, templates, snapshots, pause and resume, and metadata
  labels.
- **Architecture is part of the image contract**: gVisor doesn't emulate, so the port's image
  reference must name the platform, and stackr builds one image per host architecture.

### Forge port

- Change requests, checks and the content API mapped cleanly onto Forgejo: draft is a title
  prefix there (a capability: `draft: native | title_prefix | none`), and checks are commit
  statuses (a capability: `checks: runs | statuses`).
- The forge port **does not push**. The credential proxy does, so it belongs beside the forge
  port as its own component with one forge-specific part: how the credential is added (Forgejo:
  basic auth with a token; GitHub: an installation token).

### Coding agent port

- **The session model is ACP's** and opencode maps onto it: a prompt runs to a stop reason; the
  agent sends updates (`agent_message_chunk`, `tool_call`, `tool_call_update`, `plan`,
  `usage_update`) and requests (`request_permission` with `allow_once | allow_always |
  reject_once`). opencode's `permission.asked` carries `patterns` and `always` (the pattern an
  "always" would save), which the normalized permission request should keep.
- **Lattice reconciles, and doesn't trust the stream**: the port's contract is "updates are
  hints; `status()` and `pending_permissions()` are the truth", so the opencode adapter polls,
  and the ACP adapter, whose updates arrive on the same pipe as the answer, gets that for free.
- **Edits are on disk**: the port reports file edits as hints too, and the diff, the commit and
  the push are lattice's, from git, for every agent.
- **Model wiring declares the wire API** (`openai_chat`, `anthropic_messages`,
  `openai_responses`), and LiteLLM's route must match it; the Anthropic Messages route needs
  `drop_params` today. The conformance suite should run each adapter against a scripted stub
  like this spike's, through LiteLLM.
- **Pin opencode's version and its API surface**: the adapter targets one of its two surfaces
  (`/session/...` or `/api/session/...`), and its conformance tests fail on an upgrade that
  removes it.

### IDE port

Not exercised. Nothing here changes #893's proposal; the sandbox port's `expose(port)` is what
it needs.

### Where the proxies sit

Both outside the sandbox, on a network the sandbox shares with nothing else, as reverse proxies
the agents' configuration points at, so no TLS interception is needed for git or LiteLLM:

- **The credential proxy** owns git policy (repository, branch, no deletes, no tags, and
  ancestry for force-pushes, which needs a mirror), answers refusals in git's `report-status`,
  and logs each ref update with the session.
- **The egress proxy** adds the model key (stripping `Authorization` and `x-api-key` from the
  sandbox), allows LiteLLM's `/v1/*` only, and, as a forward proxy, the registries a tenant
  enables.

## Risks

- **gVisor on the target hosts**: it ran here only nested and under systrap; KVM-less Linux
  hosts are the target and remain untested, as are toolchains heavier than git and Node (Go,
  Python builds), and file-watcher-heavy dev servers.
- **opencode's API stability**: two surfaces, a deprecated permission endpoint the plans cite,
  and three event streams, in one release. Pin it, and test the pin.
- **ACP's coverage**: the agent didn't use the client's `fs/*`; Claude Code auto-allowed `ls`
  where opencode asked, so the same neutral policy gives different asks per agent; and its model
  wiring through LiteLLM needs per-route quirks.
- **Force-push policy** depends on a mirror in the proxy or on the forge's protection.
- **OpenSandbox overlaps** with lattice's planned vault and egress pieces; two places for the
  same rule would drift.

## Recommendations

For **#893**:

1. Make ACP's session shape the coding agent port's normalized model, with opencode's native
   adapter mapping onto it; keep `patterns` and `always` on permission requests.
2. Write "events are hints, reconcile with status and pending asks" into the port's contract and
   its conformance suite.
3. Keep "lattice owns git state" and drop "ACP's file-system methods are served from the
   sandbox" from #895 unless an agent is found that uses them.
4. Give the credential proxy its own section: ref-name policy from the commands, ancestry from a
   mirror, refusals as `report-status`, the forge-specific part only for adding the credential.
5. Add `draft` and `checks` capabilities to the forge port, as above.
6. Run every adapter's conformance suite against a scripted stub model through LiteLLM, so CI
   needs no model key.
7. Finish #899's first criterion on GitHub before the RFC leaves Discussion.

For the platform RFC's **vault (#942)** and **egress (#943)** parts:

1. Decide whether OpenSandbox's `credential-vault` and `networkPolicy` are adapters behind
   lattice's secrets and egress ports or are bypassed. The recommendation: lattice keeps the
   policy and the audit, and the sandbox adapter translates egress rules into `networkPolicy`
   where it exists; credentials stay in lattice's proxies, because host-and-path header
   injection can't express git's ref policy.
2. Prefer reverse proxies with fixed upstreams (no TLS interception) for anything the agent can
   be configured to call; use a forward proxy with an allowlist only for registries.
3. Have the egress proxy strip every credential header the sandbox sends (`Authorization`,
   `x-api-key`, and the forge's), not only replace one.
4. Log each proxied request with tenant, workspace and session, as #885 asks; the spike's proxy
   logged ref updates, which is the record a person needs after a refused push.

## How to run it again

On a Linux host with Docker and `runsc` (or Docker-in-Docker as here), with a random token `T`
in every name: create an internal network and an external one; start Forgejo on the external
one and create a user, a token and a repository with its CLI and API; start `stub_model.py` and
LiteLLM with `litellm.yaml`; start `proxies.py` on both networks with the variables its
docstring lists; start the sandbox from `Dockerfile.sandbox` on the internal network only, clone
through the proxy and copy `opencode.json` in; run `opencode serve` in it; then
`drive_opencode.py` from a container on the internal network, and `drive_acp.py` from the host.
Remove everything by its exact name afterwards, with `docker rm -fv` so anonymous volumes go too.
