# ADR-0095: A run that waits on nothing is failed, and a message that starts nothing is told

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0042](0042-typed-run-failures.md) with two reasons; [ADR-0070](0070-a-runner-looks-again-for-what-a-dead-holder-was-asked.md), whose `recover` now ends the runs a dead process left; [ADR-0057](0057-a-turn-acts-for-one-author.md), whose passed-over message is now announced

## Context

The owner watched a thread show nothing for five minutes: "It's also been working for 5 mins but I see no progress... Sitting and waiting for 5 mins is unacceptable." The live stack showed how a run can go quiet without anything saying so:

- **A model that sends nothing holds the thread for as long as the client library waits.** The runner streams every request, but nothing in artifactr timed the stream: a request that never answered, or a stream that stopped mid-reply, waited for LiteLLM's ten-minute request timeout, with the thread claimed and `welcome` listing the run as active. The gateway's log showed one chat completion in ten hours while runs were "working".
- **A tool that never returns does the same, for ever.** Native files' workers, connected apps and converters are called with no deadline.
- **A message whose turn was refused was silent.** `authorize` can refuse the agent's start on an author's behalf ([ADR-0057](0057-a-turn-acts-for-one-author.md)); the runner passed the message over, logged it at `INFO`, which the deployment doesn't show, and recorded nothing. The thread looked idle, and the person waited.
- **A run a dead process left `running` stayed so until someone posted in its thread.** `recover` ([ADR-0070](0070-a-runner-looks-again-for-what-a-dead-holder-was-asked.md)) took what was asked and not taken, but a run in a thread with nothing asked was left as it was, listed as active in every `welcome`, and watched by every connection. stackr's template never called `recover` at all: the portal is multi-tenant, and tenants are grantr's.
- **A stopped or failed run recorded no usage.** Only a completed or paused run did, so what a long failure cost was unknown.
- **A token-at-a-time model sent a frame a token.** A run's buffer of 1,024 frames was a few sentences, so a client that reconnected mid-reply was sent the tail of the reply twice, with nothing to place it by, and a slow connection was closed with 4429 as often as it reconnected until [#787](https://github.com/alexnodeland/lattice/pull/787) made live frames wait for room.

## Decision

- **A turn is timed, and a wait that runs out fails the run with a typed reason.** `Runner(liveness=Liveness(...))` sets the waits, in seconds: `first_output` (120) to a model request's first event, `no_output` (120) between its events, `local_first_output` and `local_no_output` (300 each) for a model served locally, and `tool` (600; `None` waits as long as a tool needs) for a tool call's return. The runner wraps each turn's event stream: the events of each model request are pulled in a task of their own, so a wait that runs out cancels that one pull, which tears the request down, and raises `ModelStalled`, a `RunFailure` with the reason `model_stalled`; a tool call's result that doesn't come raises `ToolStalled`, `tool_stalled`, and cancels the calls still running. The run ends as any typed failure does ([ADR-0042](0042-typed-run-failures.md)), its usage so far recorded, and the thread is released for the next message. The error says which model, or tool, and how long it waited, in words a reader can act on, and never a URL or a key ([ADR-0084](0084-what-a-run-records-of-its-calls-and-who-reads-it.md)); a tool round's error names every call still running as the wait ran out, once each; which one stalled isn't known. A call deferred to a person (`CallDeferred`, `ApprovalRequired`) sends no result and stays among them, so beside a call that really hung it is named too; it never holds the wait open alone, since its round's stream ends with `DeferredToolRequests` and the tool wait never runs against a person. A `HandleDeferredToolCalls` resolver that answers inline, inside the stream, would need handling here. A tool round is timed by `tool`, not by the model's waits: a tool that takes three minutes is not a stalled model. The owner decided the model waits; the tool wait is this record's own, from the evidence, and stackr's template reads it from `AGENT_TOOL_SECONDS` (`none` waits as long as a tool needs) so a deployment whose workers legitimately take longer raises it.
- **The model is classed by the name the run context gives,** `ctx.model.model_name`, which is the gateway's alias through LiteLLM. Falling back between providers is the gateway's job today ([ADR-0031](0031-litellm-proxy-first.md)); pydantic-ai's `FallbackModel`, whose name joins its models', is not used, and a deployment that used one would class it by `local_models` or `hosted_models`, or the primary's hang would be failed at the hosted wait before the fallback answered.
- **A model is local by its name, with the application's say as the last word.** `is_local_model(name, local=..., hosted=...)` counts LiteLLM's local providers' prefixes (`ollama/`, `lm_studio/`, `omlx/`, `llamacpp/`, `vllm/`) and the gateway aliases `local`, `local-*` and `local/*` as local, and any other name, an unknown one among them, as hosted; `Liveness(local_models=..., hosted_models=...)` names exceptions by exact name, and `hosted` wins over `local`. The owner set the defaults: 120 seconds hosted, 300 local, both waits, as settings. stackr's template reads them from `LITELLM_FIRST_OUTPUT_SECONDS`, `LITELLM_NO_OUTPUT_SECONDS`, `LITELLM_LOCAL_FIRST_OUTPUT_SECONDS`, `LITELLM_LOCAL_NO_OUTPUT_SECONDS`, `LITELLM_LOCAL_MODELS` and `LITELLM_HOSTED_MODELS`. The gateway's `default` group classes as hosted unless named local.
- **A message whose turn is refused is announced.** `_refused` logs the refusal at `WARNING`, with the action refused, and posts a notice in the thread as the runner: "The last message got no reply: whoever sent it isn't allowed to start the assistant in this thread. Ask someone who can start the assistant to send it again." A notice starts no turn and the agent is not told of it unless its capability asks ([ADR-0051](0051-notices.md)). A notice the runner may not post is logged, and the turn is still skipped. The notice says why in people's words, never the action's name, and ends with what to do next, as portalr's [ADR-0070](../../portalr/adr/0070-a-servers-words-never-reach-a-reader.md) asks of an error; the log says the rest.
- **`recover` ends the runs a dead process left.** After it has taken what was asked, it records each run still `running` in the workspace as failed, `abandoned`, once its thread can be claimed, as the thread's next turn would have ([ADR-0020](0020-running-agents-in-threads.md)). A thread another claim holds, as a dead process's is for up to `claim_ttl` after it died, so a restart's first look usually finds it, is swept once more `look_again_after` later, by when a dead claim has lapsed; a live holder's thread is left to it, as it records its own run's end. A run of this process is left alone. Its usage went with its process, so it has none. stackr's template calls `recover` the first time each workspace opens in a process, in the background, acting as the system: the portal's tenants are grantr's, so it can't page through them at startup.
- **Every `run_ended` carries `usage`.** A stopped or failed run records what it used so far, from the run context's cumulative usage; a completed or paused one records the whole, as before. `RunUsage` gains `cache_read_tokens` and `cache_write_tokens`, both 0 where the provider doesn't say, as in events recorded before; the model, the reasoning tokens and the per-step breakdown are a later record's.
- **Deltas are gathered for 50 milliseconds and carry their offset.** `forward_live(channel, coalesce=0.05)` gathers a part's text and thinking deltas and sends them as one; any other event sends what is gathered first, so frames keep the stream's order, and the stream's end sends the rest. `text_delta` and `thinking_delta` gain `offset`. The rule: **`offset` is where the delta starts in its part, in UTF-16 code units, as a browser's string indexes count them (an emoji outside the Basic Multilingual Plane is two), counting from 0 at each `part_started`**; a model response's parts are numbered from 0 again, so a part is known by its response and index, as the client already tells responses apart, and the offsets of one response's part 0 say nothing of another's. A client keeps each part's text and writes a delta at its offset, `text[:offset] + delta`, so one sent twice, as a run's buffered frames are on reconnect, lands once; a delta past the end of what the client has, after a frame it was never sent, as a thinking frame the connection shed, is appended; a delta without an offset, from an earlier server, is appended too. `offset` is optional, so the protocol is unchanged for a client that ignores it.
- **Thinking is shed first.** A connection whose outbox is more than half full drops `thinking_delta` frames before any other: thinking is never kept, and the reply's text matters more. Live frames wait for room as [#787](https://github.com/alexnodeland/lattice/pull/787) made them; 4429 keeps its meaning, a client too slow for events, results and errors, or that leaves live frames no room for 30 seconds.
- **`welcome.active_runs` entries carry `started_at`**, when the run's latest turn started, from its `run_started`, so a client can say how long a run has been going. It is read back from the run's thread, as the turn to watch already was, and only for the runs in threads the client follows: a run it doesn't follow is listed with no `started_at`. Which model answers is a later record's, with the per-message model.

Every field is optional with a default, so the protocol stays `artifactr.v1`, and an event from an earlier version validates.

## Options considered

### Option A: Time the stream in the runner, as a wrapper of the event stream handler (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one wrapper, no change to pydantic-ai's graph or the capability |
| Coverage | Every model request of every turn, through any model; tool rounds by their own wait |
| What a failure says | A typed reason, the model or tool, and the wait |

**Pros:** pydantic-ai opens each request lazily as its stream is first pulled, so the wait to the first event covers the connection too; cancelling the pull tears the request down through the library's own path.
**Cons:** a model that sends keep-alive events without content is never a stall; that is accepted, since it is sending.

### Option B: The client library's timeout

LiteLLM's `request_timeout`, 600 seconds, or an `httpx` timeout on the model.

**Cons:** ten minutes is the wait the owner refused; a shorter one applies to a whole request, not between events, so a long reply that streams is cut short; and the failure would be an opaque error, not a reason.

### Option C: A watchdog task that cancels the run

A task that watches the time of the last frame and cancels the run's task.

**Cons:** a cancelled run records `stopped`, not `failed`, and no reason: the capability's `wrap_run` would have to tell a stall from a stop.

### Option D: A snapshot frame on watch, instead of offsets

A `part_snapshot` of each part's text so far, sent as a watch starts, in place of replaying buffered deltas.

**Cons:** the channel would have to keep each part's text as well as its frames; offsets make the replay idempotent with one optional field, and a snapshot can be added beside them later: the design is the channel keeping, per run and part, the text so far, and `watch` sending one `text_delta` per part at offset 0 in place of the buffered deltas, which the offset rule already lets a client apply. It would also close the gap a buffer's first delta leaves when a part began before the buffer.

## Consequences

- A run can no longer wait silently on a model or a tool: it fails within the configured wait, says why, records what it used, and releases its thread. A legitimately long tool gets ten minutes by default, or as long as the application allows.
- A person whose message is passed over is told so, in the thread, at once.
- A replacement process ends the runs its predecessor left, so `welcome` lists only runs that are going.
- Clients see fewer, larger live frames, and a reconnect no longer doubles the tail of a reply if they apply offsets; portalr's client appends until it does.
- Harder: a tool that legitimately takes longer than `tool` needs the application to raise it, or set it to `None`.
- Revisit: the model's identity per step and the per-step usage (phase C of the streaming work); a per-message model (phase D) adds `model` beside `started_at` in `active_runs`, and changes the name the watchdog classes by; a snapshot frame if the buffer's gap proves to matter; a per-model wait read from the gateway's model info rather than the name; a rate limit on the refused-turn notice, which a client that keeps posting as someone who may not start a turn would make one of per message.
- The thread claim's spec is unchanged: `recover`'s sweep claims a thread as any claimant does, and releases it as it ends.

## Action items

1. [x] `Liveness`, `is_local_model`, `ModelStalled`, `ToolStalled` and `watched`, and `Runner(liveness=...)`.
2. [x] `_refused` posts a notice and logs at warning level.
3. [x] `recover` abandons the runs a dead process left; stackr's template recovers each workspace as it first opens, and reads the waits from settings.
4. [x] Usage on every `run_ended`, with the cache fields.
5. [x] Coalesced deltas with offsets; thinking shed first; `started_at` on active runs.
6. [ ] portalr's client applies offsets (phase A's text-part work).
