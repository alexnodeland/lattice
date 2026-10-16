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
- pydantic-ai writes them as span attributes, and not as span events: `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.call.arguments` and `.result`. Other things that span may carry hold what was said too, and under names no list of ours can keep up with: `pydantic_ai.all_messages`, `final_result`, `tool_arguments`, `tool_response`, an older `gen_ai.prompt` and `gen_ai.completion`, a request's or a response's body, a SQL statement, an exception's message, and what a library or a later version adds.
- Tempo answers a trace's search with ids that have lost their leading zeros; in the test stack, a trace's read with each span twice; and its OTLP JSON with spans' ids in base64.

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
- **A trace read shows only what is known to be safe, and the rest is read for one span, when asked.**
  - `GET /portalr/v1/traces/{id}` gives a span the attributes on a list of those known not to hold what a person or a model said: ids, kinds, outcomes, counts, models, tools, HTTP methods and statuses, a database's system and operation. Every other attribute is withheld, and named in the span's `withheld`. A prompt or an attribute that doesn't exist yet is withheld by not being on the list, so the gate fails closed. A test holds it against a span that carries each of the names above.
  - `?content=true&span=<id>` gives that span's other attributes, and no other span's. Content without a span is a 422. It is answered with `Cache-Control: no-store`, and `client` reads it with `gcTime: 0`, so it isn't kept.
  - The trace page reads the structure. A span with something withheld lists the names, and offers "Show what this span withheld", which reads the trace for that span alone and shows its attributes, each labelled, JSON indented. Another span still offers its own, and shows nothing of what it withheld, in the page or in what was sent to it. A scenario holds that, by the bodies of the answers.
  - A trace's page is keyed by its trace's id: opening another is a page of its own, with nothing asked and nothing chosen.
  - So what a span withheld leaves the server only for the span, and the person, that asked. It is the tenant's own data, which its owners and admins may read in Tempo's and Langfuse's own UIs; the reveal is a rule of this view, not of the data. Reading it is a read of the trace again, and Tempo's answer is the same size.
- **`GET /portalr/v1/traces` and `/traces/{id}` repair what Tempo gives.** A trace's id is 32 lowercase hex digits wherever it is written, in one type for a search's ids and a trace's, and `client` reads a trace by that form, so one trace is one read, however a link writes its id. Its spans are each once, the first, and their ids are hex, not base64. Each is tested.
- **A trace read is bounded.** At most 5,000 spans are given, the first, and the trace says it isn't complete, as the page does; whose it is, is decided over every span first. Tempo has 10 seconds to answer, past which it is unavailable. A trace of a tenant's turn is far smaller, and a trace of a runaway isn't a page to wait for.
- **Traces is `/t/$tenant/traces` and `/t/$tenant/traces/$trace`,** on the rail where `portalr:read_telemetry` is allowed, gated in `beforeLoad` and read in `loader`.
  - The list is the newest 100 in the last hour, day or week, or a thread's or a run's, newest first, each with when it began and how long it took, as a table or, on a phone, cards. The window is read to the next whole minute, so a read of it is one query for a minute.
  - The window and the filters are in the address, as Feedback's are. An id that isn't one portalr takes is none.
  - A list at its limit says it is the newest, not all.
  - The trace id in Feedback's comments opens its trace here, for every tenant admin. For operators, Langfuse's page is beside it.
- **A trace's tenant is decided over every span as Tempo gave it,** before any is dropped for repeating an id, in hex or in base64: a span of another tenant's that reuses an id is still another tenant's, and the trace isn't served.
- **A family of counts shows numbers alone:** `gen_ai.usage.*` shows an attribute only if its value is a number, so a name made up under it that holds text is withheld.
- **A span's name is shown as it is, cut to 200 characters.** This is an accepted residual: instrumentation sometimes puts a query, a URL or a message in a name, and a name is how a span is told from another in the tree. The libraries' own names are commands and operations. It is cut, not withheld; a deployment that puts content in names has the same exposure in Tempo's own UI.
- **Events aren't read.** A span's events, where an older or a different instrumentation puts a prompt, aren't in the trace read, so they are neither shown nor withheld, and a span's reveal can't show them. The panel says only that the read returned none of the attributes it asked for.
- **The list says nothing of a trace's root:** portalr leaves its service and name out, since a root may be another tenant's span, and a trace that isn't the tenant's is not shown.
- **The scenarios:**
  - A failed turn is made, and checked to have failed. Traces is read until its trace is there, as Tempo takes a moment, and it opens as a tree.
  - A trace with a prompt, under `gen_ai.input.messages` and `pydantic_ai.all_messages`, is sent to Tempo's OTLP receiver. The prompt is in neither the page nor any answer the page got, until that span is asked for.
- **Feedback's thumbs chart keeps its labels whole on a phone:** a direct label's room is 7px a character, not 6.

## Options considered

| Option | For | Against |
|---|---|---|
| **Write `TraceView` for `ui` (chosen)** | Ours to change; Tailwind 4 and Base UI from the start; no port, no licence | The tree, the keys and the waterfall are ours to test and keep |
| Port AgentPrism's source, as the RFC says | Its look, and its details tabs | A Tailwind 3 and Radix alpha to rewrite and then follow, for a view we then shape to our spans anyway |
| Use AgentPrism's `data` adapter | Its categories | It takes OTLP whole, which portalr doesn't give, and reads none of our content |
| **Only what is known safe, the rest for one span on its ask (chosen)** | A prompt, or a name that doesn't exist yet, never leaves the server unasked; fails closed | A read for each span that asks; the list is ours to keep |
| A list of the names that hold content | Nothing harmless is withheld | Fails open: every name missed leaks, and pydantic-ai, its older versions, and the libraries add names |
| Content in every trace read, hidden by the UI | One read | A prompt in the page, and in the network log, of everyone who only opened a trace |
| No content at all | Nothing to leak | A trace of what the agent said can't be read |

## Consequences

- Easier: a tenant's admin follows a turn span by span, from a thread's id, a run's, or a feedback comment, and a long trace stays fast.
- Easier: a prompt is seen only by someone who asked to see it.
- Harder: the applications that record content do so for every tenant's traces, which is theirs to decide, as `include_content` is.
- Harder: our adapter follows the GenAI conventions as pydantic-ai writes them. A later version that records content in span events, not attributes, would show none, and nothing says that it was recorded: the trace read gives span attributes alone.
- Harder: a span with an attribute that isn't on the list, harmless or not, offers to show it, until it is added to the list.
- Harder: a trace read of a span is a read of the whole trace, and Tempo's answer is as large for one span's reveal as for the page.
