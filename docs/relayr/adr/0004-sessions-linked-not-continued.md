# ADR-0004: Sessions linked, not continued

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Records decision D4 of [stackr RFC-0002][rfc-0002], the combined system.

## Context

Each library has its own idea of a session. In artifactr it is the thread, and a turn is its own trace ([artifactr ADR-0035][a-adr-0035]). In reflexr it is the causal chain, and a trace is a run attempt ([reflexr ADR-0018][r-adr-0018]). A story that crosses the bridge touches both.

## Decision

- **Separate traces and sessions, with links between them.** A chain does not join the thread's Langfuse session, and neither library's session model changes.
- **Tags join them:**
  - a run that starts from a thread event is tagged `thread:<id>`
  - a turn that relayr starts is tagged `chain:<correlation id>` and `rule:<name>`
  - LiteLLM metadata follows the same tags
- **The Langfuse user** of a run started from a bridged event is the event's author, not the bridge's source actor.
- **relayr wraps each library's Langfuse context** (artifactr's `turn_context`, reflexr's run context) to add its tags and set the user, so neither library changes.
- **Model history stays apart.** A chain never joins the thread's model history; the agent learns of a chain's work through change notes, proposals and notices.

## Options considered

| Option | For | Against |
|---|---|---|
| **Linked, not continued (chosen)** | No change to either library's session model. Scores stay with what they judge | Two sessions to open for one story, joined by tags and links |
| One Langfuse session for a thread and the chains it starts | One view | Needs a session resolver port in reflexr, mixes chain and thread scores, and a chain fed by several threads has no single session |
| The chain continues the conversation (shares the model history) | The agent sees everything | A second author inside the conversation, with none of the thread's review |

## Consequences

- Easier: each library's traces, sessions and scores keep meaning what they mean today.
- Harder: following one story means opening two sessions, joined by tags and span links.

[a-adr-0035]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0035-a-turn-is-its-own-trace.md
[r-adr-0018]: https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0018-opentelemetry-observability-with-langfuse.md
[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md#d4-sessions-linked-or-continued
