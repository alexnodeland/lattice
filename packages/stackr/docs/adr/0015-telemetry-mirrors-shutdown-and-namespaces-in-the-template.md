# ADR-0015: Telemetry, mirrors, shutdown and namespaces in the template

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[ADR-0011](0011-the-application-template-in-detail.md) left the database driver uninstrumented, because the libraries polled their storage and each poll would have been a trace of its own. It kept Langfuse's client from exporting spans with a span filter of the template's own, and started a feedback mirror per workspace that read the log from the start each time. It named the polls and the mirror's missing cursor as things to revisit.

The libraries have since changed all three (artifactr [ADR-0046](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0046-telemetry-that-composes-across-libraries.md), reflexr [ADR-0040](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0040-telemetry-that-composes-across-libraries.md)):

- Each library contributes its metric views and the instrumentations it advises to one `configure_telemetry`.
- They poll untraced, so the driver's instrumentation traces no poll.
- `langfuse="scores"` sends Langfuse scores and trace attributes but no spans.
- A `FeedbackMirror` carries on after a named cursor.

artifactr's `Runner` also owns its runs now, and `Runner.aclose()` stops them at shutdown; a closed runner starts no turn ([ADR-0047](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0047-cancel-safe-storage.md)).

reflexr now names every event type and rule in a namespace, `namespace:name`, declared once per process on an abstract base, and reserves `reflexr` for its own facts ([ADR-0039](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0039-namespaced-event-types.md)). A generated application needs one.

## Decision

- **One `configure_telemetry`, with the libraries' contributions.** When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, `telemetry.configure` calls it once. With both libraries it is artifactr's, given `reflexr.otel.telemetry()`; artifactr's adds its own contribution. It instruments what the libraries advise, FastAPI, SQLAlchemy and httpx. `create_app` instruments the application and its database engine itself, since both exist before instrumentation could patch them. A turn's or run's trace shows its queries, and an idle application exports no spans.
- **Langfuse gets scores only: `langfuse="scores"`.** Its client sets each turn's and run's session, user and tags on the spans and records scores, and exports no spans. Traces reach Langfuse through the Collector only, as [ADR-0007](0007-how-telemetry-reaches-the-backends.md) routes them.
- **Mirrors keep a cursor, and every surface starts them.** Each library's mirror saves its cursor, `langfuse`, in the workspace, and a restarted application carries on after it; each library keeps its cursors in a table of its own. Each library's router and MCP server take the same `authorize` hook, so a workspace first used over MCP is mirrored too.
- **The shutdown order.** Each library's part stops the same way, reflexr's first, and the database engine is disposed last:
  - Its MCP server stops, so no command arrives that the library could no longer carry out. A closed runner starts no turn, so a tool call after it would post a message whose turn never runs.
  - Then its work stops. reflexr's reactor stops gracefully, as ADR-0011's amendment on it decided; `runner.aclose()` stops artifactr's turns still going, each recording that it stopped.
  - Then its mirrors close.
- **reflexr's namespace is the package's name.** A generated application's events subclass an `AppEvent` base declared with `event_namespace="<package>"`, and its rules are named `<package>:<rule>`: `my_app:ticket.opened`, `my_app:triage`. The package's name is already a valid namespace and the default database schema, and it is the application's own, so it needs no question.

This supersedes, in ADR-0011:

- in its Telemetry bullet, the span filter, the uninstrumented driver, and artifactr's `configure_telemetry` setting up both libraries without reflexr's contribution;
- in its Evaluation data bullet, the mirrors' start "through the routers' `authorize` hook";
- in its Consequences, the untraced driver, and the storage polls and the mirror's cursor among the things to revisit;
- in its amendment on the reactor's graceful stop, the MCP server closing after the reactor: it now closes before.

The rest of ADR-0011, and of its amendments, stands.

## Options considered

### Telemetry

| Option | Queries in traces | A trace per poll | What the application sends Langfuse |
|---|---|---|---|
| **One setup with contributions, the engine instrumented, `langfuse="scores"` (chosen)** | Yes | No | Scores and trace attributes |
| The template's instrument list and span filter (ADR-0011) | No | No | Scores and trace attributes, through a filter of the template's own |
| `langfuse="traces"` | Yes | No | Every span, which the Collector sends too, so each arrives twice |

### reflexr's namespace

| Option | Unique to the application | A question |
|---|---|---|
| **The package's name (chosen)** | Yes, as its package is | No |
| A question of its own | As the person answering makes it | Yes |
| A fixed name, such as `app` | No: two applications in one process would declare it twice | No |

## Consequences

- Easier: a turn's or run's trace shows its queries, and the template carries no telemetry code beyond one call.
- Easier: a restarted application doesn't send every score again.
- Easier: an MCP client's workspace is mirrored and authorized like any other.
- Easier: an application's event types and rules never clash with a library's or another application's.
- Harder: queries outside a request, turn or run, such as the migrations at startup, are traces of their own.
- Harder: a slug that is a library's name would give the application that library's package name, and `reflexr` would take reflexr's reserved namespace, so the `project_slug` validator has to refuse the libraries' names.
- Revisit: a mirror that follows every workspace of a tenant, which would be a library change and would replace the template's `Mirrors`.

## Action items

1. [x] Refuse the libraries' names, `artifactr`, `artifactr-ai`, `reflexr` and `evalr`, in the `project_slug` validator.
