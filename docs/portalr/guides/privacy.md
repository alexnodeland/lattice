# What portalr keeps from view

portalr shows people what an agent did, and an agent's work holds what people and models said. So portalr's reads are built to show **structure and numbers by default, and content only when it is asked for**, one item at a time. This page says what is withheld, how to ask for it, and what isn't withheld. Each default **fails closed**: a name or value portalr doesn't know to be safe is withheld, not shown ([ADR-0030](../adr/0030-traces-and-the-trace-view.md), [ADR-0031](../adr/0031-logs-and-health.md)).

## Every read is the tenant's own

Each read of a tenant's data names the tenant, grantr checks that the caller may read it, and every query is built with the tenant first. portalr's `readers` module is the only code that talks to Tempo, Loki, Prometheus, Langfuse and LiteLLM. A test builds every query each reader can send and fails if one lacks its tenant, and the acceptance tests read two tenants' data as each and find neither sees the other's ([ADR-0006](../adr/0006-shared-stores-every-read-filtered.md)). A record or trace that mentions another tenant is not shown: the tenant is decided over every item before anything else is done with it.

## Traces

A span shows its **structure, timings and tokens**. The read gives a span only the attributes on a list known not to hold what a person or a model said: ids, kinds, outcomes, counts, models, tools, HTTP methods and statuses, a database's system and operation, and `gen_ai.usage.*` counts *only if the value is a number*. Every other attribute, a prompt, a completion, a tool's arguments or result, an exception's message, a SQL statement, and whatever a library adds next, is **withheld and named** in the span's `withheld`. A prompt under a name nobody has listed is withheld by not being on the list.

To see a span's withheld attributes, choose the span and **Show what this span withheld**. That reads the trace again for that span alone (`?content=true&span=<id>`), answered with `Cache-Control: no-store`, and the browser keeps it no longer than the span is shown. Another span still offers its own button and shows nothing of what it withheld, in the page or in what was sent to it. Opening another trace is a page of its own, with nothing asked.

Two things are not withheld: a span's **name**, which is cut to 200 characters (instrumentation sometimes puts a query or a message in one), and the owners' own ability to read the same data in Tempo and Langfuse. A span's events, where an older instrumentation puts a prompt, are not read at all.

## Logs

A log read gives each record its **time, level, service, thread and run, and the length of its line**, with the labels known to be safe. It does not give the line, not even a preview, and the labels are gated twice: a label's **name** must be on the list, and its **value** must be plain: an id must match an id's form, a level must be one of `trace`, `debug`, `info`, `warn`, `warning`, `error`, `fatal` or `critical`, and a name must be short and plain. One that fails is withheld and named.

A line is read for one record when you choose **Show this line** (`GET /v1/logs/{record_id}`, `no-store`), and kept only while shown. A record's id is made of its time, a digest of its shown labels and its place among that stream's records at that instant: nothing of the line, so holding ids and guessing a line can't confirm the guess. A line that isn't the length its record said is not shown.

A line shows ANSI **colour and bold** from a fixed palette checked for contrast in both schemes, and nothing else of its escapes: cursor movements, titles, links, the clipboard, backgrounds, direction marks and every other control are stripped, and it is rendered as text, never as markup.

Reads are bounded: a window of at most 24 hours, 1,000 records, and ten seconds from Loki. If it hit its limit, it says there may be more.

## Runs

A rule's run shows its status, attempts, retries and the **code** of why it last failed. Its error message is never shown: it may hold what a person or a model said, and the store never keeps it ([ADR-0032](../adr/0032-runs-in-admin.md)).

## What is shown on purpose

- **Feedback** shows the comments people left with their thumbs. They were written for the tenant's admins to read.
- **A thread, a message, an artifact** show in the app to whoever grantr says may read them; a restricted thread shows to those with a role on it.
- **An artifact's content** is the tenant's own, shown through its renderer, as Markdown without raw HTML.

## Emails and names

grantr holds no names, and portalr shows people by their grantr id, which with Supabase is the account's UUID. Emails appear in two places only: the box where you type an invitation or an owner, and Supabase Auth. portalr sends an email to Supabase to invite or find someone, and does not log it, echo it in an answer, store it, or keep it in the browser once it is used. **Showing people by email** in Members and Share (a server read of GoTrue's admin API) is planned ([issue #169](https://github.com/alexnodeland/lattice/issues/169)) and is not built, so until it lands the UIs show ids.

## The browser

- The session lives in `localStorage`, under `portalr`. The UIs' Content-Security-Policy allows only their own origin and your Supabase project, no inline script, no framing.
- `config.json` is public and holds only Supabase's *publishable* key: `Site` refuses a secret key.
- Reads that expose content are not kept: a revealed span or line is dropped when nothing shows it. An operator's links are read once each and not cached, because each is recorded.
- Markdown renders without raw HTML; links go to the web, mail, the page and the app, and images load only from the app's origin.

## Where the gate stops

Langfuse and Grafana are not tenant-scoped and have no reveal gate. An operator's links into them show content across tenants, which is why Tools carries a notice and each making of links is [recorded](operators.md#what-is-recorded). Anyone with access to those tools directly has the same reach.
