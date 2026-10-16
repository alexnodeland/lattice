# ADR-0035: Tools, links into Langfuse and Grafana, and the record of making them

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland
**Amends:** [RFC-0002](../../rfcs/0002-portalr-the-portal.md), whose operator Tools row has deep links for "any run, session or tenant" and says nothing of a notice or a record

## Context

lattice RFC-0002 gives operators Tools: deep links into Langfuse and Grafana. [ADR-0005](0005-operators-see-across-tenants.md) has operators, a grant in grantr, see across tenants, and the links only for them, because those tools aren't tenant-scoped. This is Tools (6e-ii).

What exists: `GET /portalr/v1/deployment/links` takes a trace's, a session's or a run's id and builds URLs from the Langfuse and Grafana addresses the application configured, for callers who read the deployment (`portalr:read_deployment`). Feedback uses it for a comment's trace.

What opening them skips: Traces and Logs keep a prompt, a completion and a log line out of the page until it is asked for ([ADR-0030](0030-traces-and-the-trace-view.md), [ADR-0031](0031-logs-and-health.md)). Langfuse and Grafana have no such gate. What they show, for every tenant, is what people and models said.

The user decided:

1. Tools gets a standing notice beside the links, and a server-side record of each time links are made, who and for which id. No confirmation on each click.
2. Tenant links too: Grafana Explore on Loki and on Tempo filtered by the tenant, and Langfuse filtered by its tenant tag.
3. How the record is kept follows how portalr and grantr already record things, and holds nothing of an id's content.
4. The record has the tenant's id when a tenant's link is made, since operators list every tenant already; for a trace, a session or a run, only the kind.

## Decision

- **Tools is `/deployment/tools`,** on the deployment rail of an operator, behind the deployment's layout, which lets in only whoever reads the deployment. The ids are in the address (`?trace=&session=&run=&tenant=`), so a view can be linked to, and the page is keyed by them: other ids are another page with nothing carried over.
  - It asks for a trace's id, a session's, a run's, and a tenant, chosen among the deployment's, each optional, and shows only the links the ids given make: a trace's in Langfuse and in Grafana (Tempo), a session's in Langfuse, a run's logs in Grafana (Loki), and a tenant's traces in Langfuse, and its logs and its traces in Grafana.
  - An id that isn't one portalr takes is dropped from the address, and not sent. With no id given, nothing is asked for.
  - A tool the application runs without says it has no links. A refusal, such as a tenant that doesn't exist, is said, and shows no link.
- **A standing notice is on the page whatever it shows:** "These tools are outside portalr's gates". It says the tools aren't scoped to a tenant, that they show what people and models said across every tenant, that Traces and Logs keep that behind gates which these don't have, and that links made here are recorded: who you are, which kinds of id you asked for and, for a tenant, which. It also says a visit to either tool that doesn't start here, or from a link already copied, is not recorded, because it isn't.
- **A link is an `href` only if it is http or https.** Whatever the server's answer holds, a `javascript:`, `data:` or other address, or text that is no address, is not rendered as a link. Each opens in a new tab with `noopener noreferrer`.
- **The operator gate comes before anything else.** The route's operator check runs before any id is read. A tenant that doesn't exist is refused (422) before a link is made or a record written, and so is an id that isn't one (`Id`, and grantr's form for a tenant's id).
- **No key is in a link.** Links are built from the tools' own public address and, for Langfuse, its project's id, never from the client that holds its API keys. A test gives Langfuse and LiteLLM clients with secret keys and holds that none of them appears in a link, in `config.json`, or in a refusal.
- **Each time links are made, one record is written: a structured log line on the logger `portalr.access`,** as grantr logs each audit entry on `grantr.audit`. portalr has no store of its own, so it follows grantr's other way.
  - It holds the operator's subject (its kind and id), the kinds of id asked for (`trace`, `session`, `run`, `tenant`), the tenant's id if one was asked for, and which tools a link was made for. It holds no trace, session or run id, no URL, and no key.
  - It has no `tenant_id`, so Loki labels it for no tenant, and a tenant's Logs, which read only records labelled with its own id, never show it.
  - It is written after the gate and the checks, once there is something to record: not for a refusal, for a request with no id, or where no tool is configured and so no link was made. Its `tools` are those a link was made in. A test holds each.
  - **It reaches Loki only if two things hold, and the second was not so until this change.** The application must export its logs (`configure(logs=…)` is optional in the libraries' telemetry), and the record must get past its logger's level: root's level is WARNING, and a record is dropped at its logger's effective level before any handler sees it, so an INFO record on `portalr.access`, and likewise grantr's on `grantr.audit`, never reached the exporter. A library doesn't configure logging, so stackr's application template, which owns uvicorn's `LOG_CONFIG`, now sets both loggers to INFO, and propagates them to root's handlers; its test holds that both reach a root handler with no level set by the test, and that no other logger is let through.
  - **How long it lasts is the deployment's Loki retention:** stackr's Loki keeps logs for 168 hours, seven days (`retention_period` in `deploy/loki/loki.yaml`). It is not tamper-evident, and an operator who could change Loki could change it. A durable record would be a change to grantr, a typed audit event in its storage, and a pull request of its own; this is not one.
  - Each ask is one read: the client keeps nothing of it (not fresh, dropped once nothing shows it, no retry, no read on focus or on reconnecting), so each is recorded once. The same ask made again at once is the same page and is not read twice. A page that is mounted again for the same ids, by going away and coming back, reads again and is recorded again; that is accepted, since it is a new opening.
- **The Langfuse tenant link is the traces page filtered to the tenant's tag.** Langfuse's traces page reads a `filter` query, `column;type;key;operator;value`, filters joined by commas, the value percent-encoded; the tags column is `traceTags`, type `arrayOptions`, operator `any of`, and portalr's traces carry the tag `tenant:<id>`. An `arrayOptions` value is its values joined by pipes, each with backslashes and pipes escaped, and then percent-encoded whole, so a comma or a semicolon in a tenant's id can't split a filter or a part: `a,b` is one tag, `tenant%3Aa%252Cb` in the link. The operator is written with its space, which the link's own encoding makes `%20`, not `+`. A unit test decodes the link as `filterQueryEncoding.ts` does, for ids with commas, semicolons, pipes, backslashes, spaces, accents and `=`/`&`, and finds one tag each. So for acme it is `…/project/<project>/traces?filter=traceTags%3BarrayOptions%3B%3Bany%20of%3Btenant%253Aacme`. A pipe or a backslash in the tag is escaped as Langfuse does before it encodes it. **This was checked against Langfuse 4.46.0's source** (`filterQueryEncoding.ts`, `useSidebarFilterState.tsx` and the traces filter configuration at that tag), **and pinned in a unit test; it was not driven in a live UI**, so a Langfuse upgrade that changes the format shows in that test's source check, not in it.
- **The Grafana links for a tenant or a run open at the last 24 hours** (`range` from `now-24h` to `now`), since Explore's default of the last hour would show nothing of yesterday's run; a trace's link has none, as a trace is found by its id. The links keep two shapes that are older than Grafana's newest: the pane is the `left` parameter, and its data source is the bare uid string. Both still open in Grafana's Explore, and changing them is a change to every Grafana link, so they are noted here, not changed.
- **An id in the address that portalr doesn't take is said to be ignored:** “not an id” isn't an id portalr takes, so it was ignored, with which field it was. The router rewrites an address to what was taken, so what it ignored stays in the address as `ignored`, up to 80 characters each, until the next ask.
- **The Grafana tenant links** are Explore on Loki with the LogQL portalr's own reader uses, `{service_name=~".+"} | tenant_id = "<tenant>"`, and on Tempo with `{ span.tenant.id = "<tenant>" }`, the attribute its reader filters on, the tenant quoted for each language.
- **Home's areas** gain Tools.

## Options considered

| Option | For | Against |
|---|---|---|
| **A notice and a record, no confirmation (chosen)** | An operator isn't slowed down, and every opening is on a record | A record is as good as the log's retention |
| A confirmation on each click | Deliberate | Every link is a click; operators learn to dismiss it |
| A notice alone | Simple | Nothing says who opened what |
| **A structured log line, as grantr's telemetry (chosen)** | Nothing new to keep or migrate; reaches Loki | Not durable beyond retention |
| A typed audit event in grantr | Durable, and in the deployment's audit view | A change to a library, for something grantr doesn't do |
| The id's content in the record | Answers "which trace" | An id may be a thread of a person's; its kind says enough, and a tenant's id is already known to operators |

## Consequences

- Easier: an operator opens a trace, a run or a tenant in the tools from one page, knowing what they are opening.
- Easier: who opened which tenant's logs is answerable from Loki.
- Harder: the record's life is Loki's retention, and it is not tamper-evident.
- Accepted: opening the tools is not gated beyond being an operator; the notice and the record are the control.
- Accepted: a direct visit to Langfuse or Grafana, or one from a link copied earlier, is not recorded: only links made here are, and the notice says so.
- Accepted: a deployment that doesn't export logs to Loki has no record, however the template is configured; the record's reach is the deployment's.
