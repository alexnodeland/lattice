# ADR-0003: A chat of its own

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision P3 of [lattice RFC-0002][rfc-0002], portalr, the portal.

## Context

The app's center is a chat: a thread's messages, the agent's streaming output, tool calls and approvals, and proposals inline. artifactr's thread protocol already defines all of it, with replay, resumption from a sequence number, and commands carried out once per id. A chat kit would bring its own model of messages and runs, to be mapped onto that protocol.

## Decision

- **portalr's chat is its own, and thin,** in `@portalr/ui`: the message list, streaming Markdown, the composer, tool-call and approval cards, proposal cards with accept and reject, and run status.
- **It renders what `@portalr/client`'s stores hold,** and knows nothing of the transport. The stores follow artifactr's protocol directly, through one reducer per protocol over the generated types.

## Options considered

| Option | For | Against |
|---|---|---|
| **Our own, thin, in `ui`, over artifactr's protocol (chosen)** | One model of a thread: artifactr's. Proposals, approvals and notices render as the protocol has them | More to build than a kit, and chat UX is a deep problem |
| assistant-ui, through its external-store runtime | A mature chat, with streaming, branching and attachments | A second model of messages and runs to keep in step with artifactr's, for features artifactr's protocol doesn't have |

## Consequences

- Easier: a new event in artifactr's protocol is one case in the reducer, which the compiler's exhaustiveness check asks for.
- Harder: composing, streaming and scrolling well are ours to get right.

[rfc-0002]: ../../rfcs/0002-portalr-the-portal.md#decisions
