# ADR-0016: The Threads area: a workspace's stream, and a scripted agent to chat with

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

The app's first area is lattice RFC-0002's Threads: a workspace's threads, and a chat in each, with the agent's answer as it streams, its questions and approvals, its proposals and thumbs on its messages. `client`'s artifactr store builds all of it from the workspace's stream ([ADR-0010](0010-the-client-generated-types-and-resumable-stores.md)), and `ui`'s chat renders it ([ADR-0015](0015-the-chat-components-and-streamdown.md)). Its scenarios need an agent that does each of those things on cue, against the test application of [ADR-0013](0013-the-apps-scenarios-against-the-test-application.md), which mounted grantr's router alone.

## Decision

- **A workspace's stream is open while any of its routes is.** The workspace's route opens one `Stream` on artifactr's protocol, replaying its log from the start, and closes it when the person leaves; the routes under it read the store through `useSyncExternalStore`, and send their commands on it. Its URL is made at every connect, so a reconnect carries the current token, and names the route's tenant.
- **The chat sends what its parts hand it:** `post_message`, `answer_deferred`, `respond_to_proposal`, `give_feedback` with thumbs on the agent's messages, and `create_thread` with an id the app chooses. A person's thumbs are read as the id grantr knows them by, from their memberships.
- **The test application mounts artifactr's router,** checked by grantr through its hooks, with the actors mapped as the template maps them; the runner acts as the application's own principal, which holds grantr's `application` role, so it can save its place in the log. Its streams need a WebSocket library for uvicorn, `websockets`, in its dependency group.
- **Its agent is scripted,** on artifactr's `function_model`, so each scenario chooses its path by what it posts: its words back, a question (`ask_user`), a call that waits for approval (a `publish` tool of its own), or a proposal (`edit_text` with `propose`) to one of two notes acme's `notes` workspace starts with. Every run streams, as the runner streams them.
- **`threads.feature`** covers each: starting a thread and the answer, answering a question, approving a call, accepting and rejecting a proposal, and thumbs.

## Options considered

| Option | For | Against |
|---|---|---|
| **One stream per workspace, replaying its log (chosen)** | Every area of the workspace reads one store | A long log replays in full; a thread's tail over REST comes when one is that long |
| A stream per thread, from its tail | Less to replay | A second store for the threads list and the proposals |
| **A scripted agent (chosen)** | Each path on cue, with no model | Not a real model's output |
| A model through the gateway, mocked | The real path | The Acceptance job has no gateway |

## Consequences

- Easier: each area that follows reads the same store, and adds what its scenarios need to the script.
- Harder: until phase 7, the test application's wiring of artifactr is a second one, beside the template's.
