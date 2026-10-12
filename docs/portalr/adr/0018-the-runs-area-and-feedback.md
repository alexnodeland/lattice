# ADR-0018: The Runs area, feedback on runs, and what a person may do

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives the app a Runs area, artifactr's turns and reflexr's runs, with their status, and retry, skip and cancel where allowed; and Feedback, thumbs and comments on messages, artifacts and runs. The libraries differ: artifactr stops a running turn, and nothing else; reflexr retries, skips and cancels a rule's run, and dead-letters one that fails every attempt. Their feedback has targets of their own: artifactr's a message, an artifact, a turn or a thread; reflexr's a run, a firing or a chain. RFC-0002 also has the UIs ask grantr's `/checks` what a person may do, and hide what they may not, with every command checked again by the server.

## Decision

- **The Runs area shows both libraries' runs, newest first:** artifactr's turns, each with its thread, and reflexr's rule runs, each with its rule, its attempt and how often it was retried, the dead-lettered marked; a run is as new as its first attempt. A running turn has Stop; a rule run has Retry when dead-lettered, Skip when dead-lettered or retrying, and Cancel when queued, running or retrying. A retried run is queued until its next attempt. A paused turn has no Stop, since artifactr stops only a running one: its questions and approvals are answered in its thread.
- **The workspace opens reflexr's stream beside artifactr's,** each following the session's refreshes and its end, and the Runs area reads both stores.
- **Feedback is one type, thumbs, with an optional comment,** and one `ui` component, `Thumbs`: up or down is sent as it is pressed, and why, if the person adds it, after, as the thumbs again with the comment, so the latest feedback holds both. Each library's store keeps the feedback on its own targets: artifactr's on messages, artifacts and turns, reflexr's on runs. `client`'s `thumbs` reads a person's latest from any of them.
- **Thumbs on an artifact judge one version:** each feedback keeps the version it was given on, the store keeps an artifact's latest version's alone, and the artifact's page shows thumbs for the version it shows.
- **A screen asks grantr once** for the actions its buttons need, in the workspace (`allowedIn`), before it renders, and shows only those allowed. The answer is read again as a screen mounts and as the window regains focus, since it is never fresh for long (`staleTime` 0). Its key names the tenant and the actions, not the person, which is safe because signing out clears every read. Hiding is never the check: the server checks each command, and a test sends a viewer's retry, skip and cancel and has each refused.
- **The UI follows grantr's roles as they are:** a viewer holds `give_feedback`, so a viewer sees thumbs on what they can read, and no Retry, Skip or Cancel.
- **The test application mounts reflexr's router,** checked by grantr through its hooks, with actors mapped as the template's `reflexr_subject` maps them, less stored rules, which it has none of, and a reactor running `portalr:triage` on the tickets a scenario publishes: it succeeds, or, for a ticket whose subject starts with `fail`, retries once and is dead-lettered. Its scripted agent keeps a turn running when asked to `wait`, until someone stops it. A viewer, vera, sees `notes`.
- **The scenarios find their own runs:** a ticket's run by the `seq` the publish answered, matched in reflexr's runs, and a turn by its thread, which each scenario names afresh.

## Options considered

| Option | For | Against |
|---|---|---|
| **Each library's run actions as they are (chosen)** | Nothing the libraries don't do | Turns and rule runs offer different actions |
| One set of actions for every run | One shape | artifactr has no retry or skip to offer |
| **One feedback type with a comment (chosen)** | One component; one registration per library | Its fields are the same on every target |
| A thumbs type and a comment type | Each alone | Two components, and two events for one opinion |
| **Hide what grantr refuses (chosen)** | No button that would fail | A stale answer may hide an action just allowed, until the next read |
| **Thumbs for whoever grantr lets give feedback (chosen)** | The UI holds no rule of its own; a viewer's opinion counts | A viewer sees buttons on what they otherwise only read |
| Thumbs for editors alone | Fewer buttons for viewers | A UI rule grantr doesn't have, which a deployment couldn't change by its roles |

## Consequences

- Easier: the admin UI's runs, and any screen's buttons, ask grantr the same way.
- Harder: a person who may give feedback sees thumbs on every run they can read, as grantr's viewer role allows.
- Harder: thumbs on an artifact go with its version: a new version starts with none.
