# ADR-0051: Notices: messages that start no turn

**Status:** Accepted; its direct messages amended by [ADR-0055](0055-turns-from-the-log.md)
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

A message committed directly, without `Runner.send`, starts no turn, but a running turn's watcher still passes it in, and nothing tells clients it differs from a person's message ([#63](https://github.com/alexnodeland/artifactr/issues/63)). [stackr RFC-0002](https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md) has reflexr rules post notices by default (its decision D7): information for people that must not wake or steer the thread's agent. relayr, the bridge, will post them from reflexr runs, as an `ExternalAgentActor` per rule, and runs retry. A notice needs:

- to start no turn, to steer none and to answer no paused run
- a mark that clients can show
- to stay out of the model's history, unless the application asks for it
- an id that a retry repeats, refused the second time as a message's is ([ADR-0045](0045-a-message-id-is-used-once.md))

## Decision

- **A notice is a message of kind `notice`.** `PostMessage` and `MessagePosted` gain `kind`, `"message"` (the default) or `"notice"`. That is additive to protocol v1: an optional field, with a default.
- **A notice is a message everywhere else.** It uses the message id space, so a used `message_id` is refused as any message's is (ADR-0045), and feedback targets it with `MessageTarget` ([ADR-0037](0037-feedback-targets-and-evaluators.md)).
- **The runner commits a notice as it is.** `Runner.execute` hands only a `message` to `send`, which starts, steers or answers a run ([ADR-0020](0020-running-agents-in-threads.md)). A notice is committed like any other command, so it starts no run, and it answers nothing in a paused thread. `Runner.send` posts messages only. Every surface can post a notice: the WebSocket and REST in the command, and MCP's `post_message` tool with its `kind` argument.
- **The agent isn't told, unless the application asks.** The capability's watcher passes a running turn the thread's messages, not its notices. With `ArtifactWorkspace(notices=True)`, the agent is told about the notices others post in its thread as change notes (`NoticeNote`: "timeline-entry posted a notice: ..."), when a run starts and while it runs ([ADR-0008](0008-agent-perception-and-steering.md)). A note informs the agent, where a message asks it to act, and it is kept in the history as notes are.
- **Whoever may post a message may post a notice:** every actor but an evaluator. Core checks the author of neither. A notice asks for less than a message, since it starts no turn, so there is nothing more to guard. Which rules may start a turn (D7) is decided by relayr's allowlist: a rule allowed to calls `Runner.send`, and the others post notices. A person may post a notice too, to tell the thread something the agent should not act on.

## Options considered

The mechanism:

| Option | Id space | On the wire | What branches |
|---|---|---|---|
| **A `kind` on `PostMessage` and `MessagePosted` (chosen)** | The message's, so ADR-0045 refuses a repeat as it stands | An optional field. A client that doesn't know it shows a notice as a message | `Runner.execute`'s routing, the watcher's message case, evaluation's transcript, and `change_notes`, for the opt-in |
| A `post_notice` command and a `notice_posted` event | Its own, or the message's under another name | A new event type. A client that doesn't know it keeps a notice as an unknown event, and shows nothing | Nothing in the runner or the watcher, but two new union members, their `needs` and `commit` cases, a second type for relayr to bridge, and a second renderer in every client |

How an application that asks has its agent told:

| Option | Assessment |
|---|---|
| **Change notes, when a run starts and while it runs (chosen)** | Stored in the history as notes are, and the note says who posted it and that it is a notice |
| Only when a run starts | A notice posted during a turn is never told: the next turn's briefing starts after it |
| Inserted into the loaded history by `seq` | A notice could fall between a paused run's tool call and its result, which model APIs reject |

## Consequences

- Easier: relayr posts a notice with `Workspace.as_actor(...).post_message(..., kind="notice")`, and a retry with the same derived id is refused. A bridged `message_posted` carries its `kind`, so rules can leave notices out.
- Easier: a client shows a notice by its `kind`; one that doesn't know the field shows it as a message.
- `Note` gains a member without an `artifact_id`, `NoticeNote`, so code that handles every kind of note narrows it before reading one.
- The `artifactr.messages` counter counts notices too, labelled with `artifactr.message.kind`.
- Evaluation transcripts hold a thread's messages, not its notices. A transcript attributes each message by its author's role, so a rule's notice would read as a turn of the agent's, and a replayed thread would seed it into the agent's history.

## Action items

1. [x] `kind` on `PostMessage`, `MessagePosted`, `Workspace.post_message` and MCP's `post_message` tool; the runner's routing, the watcher, `NoticeNote` and `ArtifactWorkspace(notices=)`; the counter's label, and transcripts without notices; with conformance cases.
