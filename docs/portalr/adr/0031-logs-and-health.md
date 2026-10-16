# ADR-0031: Logs without their lines, and a Health section

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland
**Amends:** [RFC-0002](../../rfcs/0002-portalr-the-portal.md), which has admin show logs with ANSI colours, virtualized, and latency and errors over time

## Context

This is the second part of admin's Traces and logs area ([ADR-0030](0030-traces-and-the-trace-view.md)): Logs, and latency and failed turns over time. Runs follow (6d-iii).

What Loki gives, looked at in the test stack:

- A line is whatever the application wrote. It may hold what a person or a model said, as a span's attributes may.
- With OTLP, Loki gives a record's resource attributes and structured metadata as the stream's labels, under dotted names turned to underscores: `service_name`, `deployment_environment_name`, `detected_level`, `severity_text`, `scope_name`, `tenant_id`, `artifactr_thread_id`, `artifactr_run_id`, and any attribute a log call adds.
- Its OTLP receiver takes a record from a test, so a scenario can send one of its own.

The user decided three things:

1. A log read gives metadata only: the time, level, service, thread and run, and the length of the line. There is no preview. The line is read for one record, when asked for.
2. A read is a window of at most 24 hours, at most 1,000 records, with 10 seconds to answer, and says whether it is complete.
3. One pull request: Logs, and a Health section with the 95th percentile of a turn's latency and failed turns, each over the last hour, day or week, with the step it is drawn at said.

## Decision

- **A log record is read without its line, and its labels fail closed.**
  - `GET /portalr/v1/logs` gives each record an id, its time, level, service, thread and run, the length of its line and the labels known to be safe: service, environment, level, scope, the tenant and the libraries' own thread, run, workspace and actor ids, a trace's and a span's id. Every other label is withheld, and named in the record's `withheld`, so an attribute that doesn't exist yet, or that holds an email, never leaves the server unasked. A test holds it against labels of each kind.
  - `GET /portalr/v1/logs/{record_id}` gives one record with its line, and all of its labels, answered with `Cache-Control: no-store`. A record's id is its nanosecond time and 16 hex digits of a digest of its time, labels and line; it is looked up in the one nanosecond it names, for the caller's tenant, so it cannot be used to read another's. An id that is no id is a 422; one that finds nothing, `null`.
  - `client` reads a line with `gcTime: 0`, `staleTime: 0`, no retry and no read on focus, so it isn't kept.
- **A record's tenant is decided before anything else.** Records come back from a LogQL selector on the tenant, and are kept only if their `tenant_id` label is the caller's, before they are sorted, filtered or counted. A record that isn't the tenant's is never shown, in a list or by its id.
- **A read is bounded.** The window is at most 24 hours (a 422 otherwise), the limit at most 1,000, and Loki has 10 seconds, past which it is unavailable. The list is newest first, and `complete` is false when the limit was reached, which the page says: a shorter window, or a thread's or a run's, finds the rest.
- **ANSI colour is rendered from a fixed palette and nothing else.**
  - A line is parsed in one pass. Of its escape sequences only the colour of the text and bold are taken: the eight foreground colours, a bright colour as the same colour, bold, reset and default. Everything else is stripped: cursor movements, clears, titles, links, the clipboard, device control strings, backgrounds, 256 and true colours, and every control character but a newline and a tab. It is rendered as text in spans, never as markup, and a hostile line is read in time linear in its length.
  - The eight colours are tokens, `--ansi-0` to `--ansi-7`, each for the light scheme and the dark, and a test holds each at 4.5:1 or more against the paper and the surface of both. A line can choose among them, and no other colour.
- **`LogList` is `ui`'s.** It is an ARIA listbox, virtualized with TanStack Virtual, so a thousand records draw a screenful. The arrow keys, Page Up and Page Down, Home and End walk it. Each row says its place (`aria-posinset`, `aria-setsize`) and, in its name, when, how bad, whose, and how long. The chosen row is the one tab stop, and the list itself is one while the chosen row is scrolled out of the window. The details of the chosen record sit beside the list, or under it on a phone; a level is a word and a shape, never a colour alone.
- **Logs is `/t/$tenant/logs`,** on the rail where `portalr:read_telemetry` is allowed, gated in `beforeLoad` and read in `loader`, with the window (1, 6 or 24 hours) and a thread's or a run's id in the address. Its body is keyed by what the address names, so another view starts with nothing asked. A record's "Show this line" reads that record alone.
- **Health is a section of that page:** a line chart of a turn's latency at the 95th percentile and a bar chart of failed turns in each step, over the last hour, day or week, from `GET /portalr/v1/metrics`. The step is picked from the window, to about 96 points: 1 minute for an hour, 15 minutes for a day, 2 hours for a week, and the page says it. A step with no turns is a gap, not a zero: portalr drops a point that is not a finite number, which Prometheus gives for a ratio of nothing. Prometheus not configured or not answering leaves the logs, and Loki's leaves the charts.
- **The scenarios:** a log record with a phrase is sent to Loki's OTLP receiver. The phrase is in neither the page nor any answer the page got until that record's line is asked for, and then it came in a read for that record alone. A second shows the charts with the step said.

## Options considered

| Option | For | Against |
|---|---|---|
| **No line in the list; a line for one record, when asked (chosen)** | A line never leaves the server unasked; fails closed | A read for each record that asks |
| A preview of each line | Easier to scan | A line is whatever was written; a preview is a leak |
| Lines in every read, hidden by the UI | One read | Content in the page and the network log of everyone who only opened Logs |
| **A list of the labels known safe (chosen)** | A new label, or one with an email, is withheld | The list is ours to keep |
| A list of the labels that hold content | Nothing harmless is withheld | Fails open |
| **Colour and bold from a palette (chosen)** | Contrast holds in both schemes; nothing can move or overwrite what's around | Backgrounds and 256 colours are lost |
| All of ANSI, or a library that renders it | Looks as in a terminal | Colours that fail contrast, and sequences that need guarding |

## Consequences

- Easier: a tenant's admin finds the log of a thread or a run, and sees how long a turn takes and how many fail, in one page.
- Easier: a line is seen only by someone who asked to see it.
- Harder: the labels list is kept as the libraries add attributes; a label not on it is read one record at a time.
- Accepted: a record's id is a digest, so two identical records in the same nanosecond are one.
