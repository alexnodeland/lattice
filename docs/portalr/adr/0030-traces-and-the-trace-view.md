# ADR-0030: Traces, and a trace view written for `ui`

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland
**Amends:** [RFC-0002](../../rfcs/0002-portalr-the-portal.md), which has the trace view as AgentPrism's components, ported

## Context

lattice RFC-0002 gives admin a Traces and logs area, and says `ui` vendors AgentPrism's components for traces, ported to Tailwind 4 and Base UI, with TanStack Virtual for long ones. This is its first part: Traces, the list and the view. Logs, and latency and errors over time, come next (6d-ii), then Runs (6d-iii).

What AgentPrism is, as it is published:

- Its `ui` isn't a package: its components are source in its repository, built on Tailwind 3 and Radix, to copy.
- Its `types` and `data` are on npm, at 1.0.0. `data`'s OpenTelemetry adapter takes an OTLP document whole, and reads `gen_ai.operation.name`, a model, a tool's name and the token counts.
- It reads a prompt from `gen_ai.request.prompt` or `input.value`. pydantic-ai records one, when asked to, as `gen_ai.input.messages`, a completion as `gen_ai.output.messages`, instructions as `gen_ai.system_instructions`, and a tool's arguments and result as `gen_ai.tool.call.arguments` and `.result`, all as span attributes. AgentPrism reads none of them.
- portalr doesn't give OTLP whole. Its trace read gives the spans of one tenant's trace, flattened, after checking that every span in it is the tenant's.

What the spans hold, looked at in the test stack:

- An artifactr turn is a trace of an HTTP span, an `artifactr.commit` span for each command, and an `invoke_workflow` span named `turn`, with `gen_ai.workflow.name`, `gen_ai.conversation.id` and `session.id`, which a thread's traces are found by. The libraries' own attributes name the tenant, workspace, run and actor.
- Prompts, completions and tool arguments are recorded only when the application sets `include_content`, which lattice-core defaults to false, though pydantic-ai's own default is true. In the test application they aren't recorded.
- Tempo answers a trace's search with ids that have lost their leading zeros, and, in the test stack, a trace's read with each span twice.

The user decided four things:

1. The trace view is written for `ui`, not ported from AgentPrism. AgentPrism's `types` and `data` are used only if their adapters really read our spans.
2. What was said in a span, its prompt and completion, is behind an explicit reveal for each span. By default, a trace shows structure, timings and tokens.
3. 6d is three pull requests: Traces, Logs, and Runs.
4. Admin's Runs offers Retry, Skip and Cancel, which the RFC didn't ask for (6d-iii).

## Decision

- **`TraceView` is `ui`'s, written for it.** It takes the shape of AgentPrism's views, a tree of spans beside a waterfall, with a details pane, but none of its code, so there is nothing to port, to keep up with, or to add a licence for. AgentPrism's `data` isn't used: its adapter takes OTLP whole and reads no content, and a dependency for three of its mappings is more than writing them. Our adapter, `client`'s `outline`, reads `gen_ai.operation.name`, the model, the tool and the token counts, as the GenAI semantic conventions say.
  - The tree is an ARIA tree. The arrow keys walk it, Left folds a span or goes to its parent, Right opens it or goes to its first child, and Home and End go to the ends. Each row says its level, its place among its siblings, whether it is open, and, in its name, what it is, how long it took, and whether it failed.
  - Its rows are virtualized with TanStack Virtual, so a trace of thousands of spans draws only those in view.
  - A failed span is marked by a word and a hatched bar, not by a tone alone. A span's kind is a mark and a word.
  - On a phone the details sit under the tree.
  - A span whose parent isn't in the trace, or that is part of a cycle, is shown as a root, not lost.
- **What was said is read apart, and when asked for.**
  - `GET /portalr/v1/traces/{id}` leaves the content attributes out, and names the ones it left out in each span's `withheld`. `?content=true` gives them.
  - The trace page reads the structure. A span that has something withheld offers "Show what was said", which reads the trace again with content, once, and shows that span's parts, labelled. A span that wasn't asked about shows nothing of it. Each part's JSON is indented.
  - So content leaves the server only for a person who asked for it, and is never in a page that was only opened. It is the tenant's own data, which its owners and admins may read in Tempo's and Langfuse's own UIs; the reveal is a rule of this view, not of the data.
- **`GET /portalr/v1/traces` and `/traces/{id}` repair what Tempo gives.** A search's ids are padded to 32 hex digits, so they match the ids elsewhere, and a trace's spans are each once, the first. Both are tested.
- **Traces is `/t/$tenant/traces` and `/t/$tenant/traces/$trace`,** on the rail where `portalr:read_telemetry` is allowed, gated in `beforeLoad` and read in `loader`.
  - The list is the newest 100 in the last hour, day or week, or a thread's or a run's, newest first, each with when it began and how long it took, as a table or, on a phone, cards. The window is read to the next whole minute, so a read of it is one query for a minute.
  - The window and the filters are in the address, as Feedback's are. An id that isn't one portalr takes is none.
  - A list at its limit says it is the newest, not all.
  - The trace id in Feedback's comments opens its trace here, for every tenant admin. For operators, Langfuse's page is beside it.
- **The list says nothing of a trace's root:** portalr leaves its service and name out, since a root may be another tenant's span, and a trace that isn't the tenant's is not shown.
- **The scenario:** a failed turn is made, and Traces is read until its trace is there, as Tempo takes a moment. Opening it shows its spans as a tree, and, as the application records no content, nothing to reveal.
- **Feedback's thumbs chart keeps its labels whole on a phone:** a direct label's room is 7px a character, not 6.

## Options considered

| Option | For | Against |
|---|---|---|
| **Write `TraceView` for `ui` (chosen)** | Ours to change; Tailwind 4 and Base UI from the start; no port, no licence | The tree, the keys and the waterfall are ours to test and keep |
| Port AgentPrism's source, as the RFC says | Its look, and its details tabs | A Tailwind 3 and Radix alpha to rewrite and then follow, for a view we then shape to our spans anyway |
| Use AgentPrism's `data` adapter | Its categories | It takes OTLP whole, which portalr doesn't give, and reads none of our content |
| **Content read apart, on a span's ask (chosen)** | Prompts never leave the server unasked | A second read, once, when a span asks |
| Content in every trace read, hidden by the UI | One read | A prompt in the page, and in the network log, of everyone who only opened a trace |
| No content at all | Nothing to leak | A trace of what the agent said can't be read |

## Consequences

- Easier: a tenant's admin follows a turn span by span, from a thread's id, a run's, or a feedback comment, and a long trace stays fast.
- Easier: a prompt is seen only by someone who asked to see it.
- Harder: the applications that record content do so for every tenant's traces, which is theirs to decide, as `include_content` is.
- Harder: our adapter follows the GenAI conventions as pydantic-ai writes them. A later version that records content in span events, not attributes, would show none, and say that it was recorded.
