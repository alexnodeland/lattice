# ADR-0084: What a run records of its calls and its failure, and who reads it

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

portalr now shows each tool call's arguments and result, and why a run failed ([portalr ADR-0053](../../portalr/adr/0053-the-chats-questions-tool-calls-sides-failures-and-streaming.md)). `ArtifactWorkspace` records them as `tool_called` and `tool_returned` summaries, and a failure as `run_ended.error`; this change raises the summaries from 200 characters to 2,000. Everything in a thread's log is read by everyone who may read the thread. Restriction is per thread and per artifact ([ADR-0062](0062-restricted-items-left-out-of-every-read.md)): a turn reads as the person it acts for ([ADR-0057](0057-a-turn-acts-for-one-author.md)). So, in a thread Alice and Bob share, Alice's turn could read an artifact hidden from Bob, and its `read_artifact` result, recorded in the thread, would show Bob what the artifact's restriction keeps from him. A failure's message can name a gateway's URL with its key in the query, or a bearer token.

## Decision

- **A call names the artifact its arguments name.** `tool_called` and `tool_returned` carry `artifact_id`, from the call's `artifact_id` argument, the name every artifactr tool and the convention for an application's take. A reader who may not see that artifact doesn't see the call, or what it returned, as an event about a hidden artifact is dropped from every read. It is an optional field, so the protocol stays `artifactr.v1`.
- **What a run failed with, and a tool's own error, are recorded without what looks like a secret:** a URL's credentials, query and fragment, a bearer token, and keys in the shapes providers give them (`sk-…`). The run's reason stays as it is.
- **portalr shows a failure's Details only to the person the turn acted for;** everyone else sees its reason. The event itself carries the redacted error to every reader of the thread.
- **A tool's author keeps the rest out:** a result is recorded, up to `max_summary_chars`, for every reader of the thread. A tool that reads what some of them may not see names it by `artifact_id`, returns ids rather than contents where it can, and keeps secrets out of what it returns and raises. `max_summary_chars=0` records no arguments or results.
- **Reasons say what happened.** `tool_retries_exhausted` is a model that kept calling a tool in ways it refused until no retries were left; `unexpected_model_behavior` is any other answer the run couldn't use.

## Options considered

| Option | For | Against |
|---|---|---|
| **The artifact on the call, dropped with it (chosen)** | Uses the one rule every read already applies | A tool that reads hidden data without naming an artifact still shows it |
| Summaries only to the turn's author | Nothing leaks to others | A filter by reader on every event, which reads have nowhere to keep; a thread's history differs by who reads it |
| Keep summaries at 200 characters | Less shown | Less to read, not less leaked |
| **Redact secrets on the server (chosen)** | Every surface, and the log, are clean | Patterns, not a guarantee |
| Hide the error from everyone but the author in the UI alone | Simple | The event still carries it to every client |

## Consequences

- Easier: a restricted artifact stays restricted through the tool calls that read it.
- Harder: an application's tool that reads restricted data names its artifact, or keeps it out of its result.
- Revisit: a list of the artifacts a result names, if `list_artifacts`' ids of restricted artifacts prove sensitive.
