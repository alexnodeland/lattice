# ADR-0018: The Runs area, feedback on runs, and what a person may do

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives the app a Runs area, artifactr's turns and reflexr's runs, with their status, and retry, skip and cancel where allowed; and Feedback, thumbs and comments on messages, artifacts and runs. The libraries differ: artifactr stops a running turn, and nothing else; reflexr retries, skips and cancels a rule's run, and dead-letters one that fails every attempt. Their feedback has targets of their own: artifactr's a message, an artifact, a turn or a thread; reflexr's a run, a firing or a chain. RFC-0002 also has the UIs ask grantr's `/checks` what a person may do, and hide what they may not, with every command checked again by the server.

## Decision

- **The Runs area shows both libraries' runs, newest first:** artifactr's turns, each with its thread, and reflexr's rule runs, each with its rule, its attempt and how often it was retried, the dead-lettered marked. A running turn has Stop; a rule run has Retry when dead-lettered, Skip when dead-lettered or retrying, and Cancel when running or retrying. A paused turn has no Stop, since artifactr stops only a running one: its questions and approvals are answered in its thread.
- **The workspace opens reflexr's stream beside artifactr's,** each following the session's refreshes and its end, and the Runs area reads both stores.
- **Feedback is one type, thumbs, with an optional comment,** and one `ui` component, `Thumbs`: up or down is sent as it is pressed, and why, if the person adds it, after. Each library's store keeps the feedback on its own targets: artifactr's on messages, artifacts and turns, reflexr's on runs. `client`'s `thumbs` reads a person's latest from any of them.
- **A screen asks grantr once** for the actions its buttons need, in the workspace (`allowedIn`), before it renders, and shows only those allowed. Hiding is never the check: the server checks each command, and a scenario has a viewer's own retry refused.
- **The test application mounts reflexr's router,** checked by grantr through its hooks, with a reactor running `portalr:triage` on the tickets a scenario publishes: it succeeds, or, for a ticket whose subject starts with `fail`, retries once and is dead-lettered. Its scripted agent keeps a turn running for a while when asked to `wait`, for a scenario to stop. A viewer, vera, sees `notes`.
- **The scenarios find their own runs:** a ticket's run by the `seq` the publish answered, matched in reflexr's runs, and a turn by its thread, which each scenario names afresh.

## Options considered

| Option | For | Against |
|---|---|---|
| **Each library's run actions as they are (chosen)** | Nothing the libraries don't do | Turns and rule runs offer different actions |
| One set of actions for every run | One shape | artifactr has no retry or skip to offer |
| **One feedback type with a comment (chosen)** | One component; one registration per library | Its fields are the same on every target |
| A thumbs type and a comment type | Each alone | Two components, and two events for one opinion |
| **Hide what grantr refuses (chosen)** | No button that would fail | A stale answer may hide an action just allowed, until the next read |

## Consequences

- Easier: the admin UI's runs, and any screen's buttons, ask grantr the same way.
- Harder: a person who may give feedback sees thumbs on every run they can read, as grantr's viewer role allows.
