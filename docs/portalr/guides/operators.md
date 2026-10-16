# An operator's runbook

An **operator** runs the deployment, across its tenants. It is a grant in grantr, on the deployment: `operator` holds `portalr:read_deployment`, `grantr:create_tenant` and `grantr:grant_operator`, and nothing in a tenant unless they are a member of it ([ADR-0005](../adr/0005-operators-see-across-tenants.md)). In admin, an operator opens on **All tenants**, which shows the deployment's areas alone: Home, Tenants, Audit and Tools. This page is what to do with them. A tenant's own owners and admins use [the admin UI](admin.md).

!!! info "How someone becomes an operator"

    From stackr's template with grantr, `make operator EMAIL=...` makes a user the deployment's first operator. After that, an operator makes another through grantr's API (`PUT /grantr/v1/operators/<user>`); admin does not do it, and neither does it delete a tenant ([ADR-0034](../adr/0034-tenants-and-the-deployments-audit.md)).

## Home

How many tenants grantr has, and what they spend across their LiteLLM teams.

## Create a tenant

Open **Tenants**. It lists every tenant by name, fifty at a time, each with its spend and its budget in words: the amount, its period and how much is spent; "No budget set" for a team with none; "No budget" for a tenant with no team at all; and a dash where LiteLLM didn't answer, with a note that spend isn't shown.

To create one:

1. Enter the **Tenant** id and the **Owner's email**. The button stays disabled until the id isn't empty and has no `~`, and the email looks like one.
2. **Create tenant** opens a confirmation that says what will happen: the tenant is created, the owner is made its first owner, Supabase Auth sends the owner an invitation *if they have no account* and finds them if they do, and a tenant can't be deleted from here.
3. **Create the tenant.** The dialog can't be dismissed while it runs, and submitting again sends nothing more. On success the page says "`<tenant>` is created, owned by `<user id>`", and the form is empty.

Behind it, `POST /portalr/v1/deployment/tenants` checks that you may read the deployment and create tenants, that the email is an email and the tenant doesn't exist, *then* asks Supabase Auth to invite or find the owner, and then asks grantr to create the tenant. A tenant that already exists is refused (422) before anyone is invited, so a repeated submit invites no one again.

What to expect:

| Answer | Means |
|---|---|
| "Not created: `<tenant>` exists" | The tenant is there. Nothing was invited |
| "Not created: the owner's email isn't an email address" | Fix the email. It is never echoed back |
| "Not created: supabase answered 5xx" (502) | Supabase Auth didn't invite or find the owner. No tenant was made |
| "the tenant couldn't be created" (503) | grantr's storage failed *after* the invitation. The person has an account (and may have an email) and no membership: retry, and they are found |
| 403 | You may not create tenants |

The owner's email goes to Supabase Auth in one request. portalr does not log it, return it, or keep it: the answer names the tenant and the owner's user id, and the page forgets the email once the tenant is made.

A tenant made here has **no LiteLLM team**, so it shows "No budget". Give it one from stackr: `make tenant NAME=<tenant>` creates the team `tenant-<tenant>` and a key, with `--max-budget` and `--budget-duration` if you want something other than 10 dollars over 30 days. Until you do, its Usage page has no budget to show.

Creating a tenant has no rate limit. It is operator-only, sends at most one email per request, and each needs a tenant name that doesn't exist yet; put a limit on the route at your proxy if you want one. An operator can also learn from it whether an email has an account, and its user id ([ADR-0034](../adr/0034-tenants-and-the-deployments-audit.md)).

## Read the deployment's audit log

**Audit** is grantr's deployment log, from `GET /grantr/v1/audit`, newest first, a page back at a time: who was made an operator and who stopped being one, by whom and when. It needs `grantr:grant_operator`, which operators hold.

!!! note "Tenant creations are not in it yet"

    grantr writes `tenant_created` in the new tenant's own log, where its owner reads it in their Audit, not in the deployment's. A change to grantr to write a deployment-scoped entry too (who made which tenant) is planned; until it lands, this view shows operators alone.

## Tools

**Tools** opens Langfuse and Grafana at a trace, a session, a run or a tenant, for the cases the tenant's own pages can't answer.

1. Enter any of a **trace id**, a **session id** (an artifactr thread's id) or a **run id**, and/or choose a **tenant**, and **Get links**. An id that isn't one portalr takes is not sent, and the page says which was ignored.
2. The page lists only the links those ids give, each opening in a new tab:

| Asked for | Links |
|---|---|
| A trace | The trace in Langfuse, and in Grafana (Tempo) |
| A session | The session in Langfuse |
| A run | The run's logs in Grafana (Loki), over the last 24 hours |
| A tenant | The tenant's traces in Langfuse (its `tenant:<id>` tag), and its logs (Loki) and traces (Tempo) in Grafana, over the last 24 hours |

A tool you don't run says "isn't configured here, so it has no links". A link is shown only if it is an `http` or `https` address, and no key of any tool is in one.

### These tools are outside portalr's gates

Beside the links, the page says it: Langfuse and Grafana are not scoped to a tenant, and they show **what people and models said, across every tenant**: prompts, completions, log lines. Traces and Logs keep that behind [reveals](privacy.md); these tools have no such gate. The control is the notice and the record.

### What is recorded

Each time links are made, portalr writes **one structured log line** on the logger `portalr.access`, the way grantr logs its audit entries:

```json
{"event": "deployment_links", "by": {"kind": "user", "id": "<operator>"}, "kinds": ["trace", "tenant"], "tenant": "acme", "tools": ["langfuse", "grafana"]}
```

It holds **who**, the **kinds** of id you asked for, the **tenant's id** if you asked for one, and the tools a link was made in. It holds no trace, session or run id, no URL and no key. It is not written for a refusal, for a request with no id, or where no tool is configured. It has no `tenant_id`, so no tenant sees it in its Logs.

What you must know about it:

- **It lasts as long as Loki keeps logs:** stackr's Loki keeps 168 hours, seven days. It is not tamper-evident. A durable record would be a typed audit event in grantr, which is a separate change that has not been made.
- **It reaches Loki only if your application exports its logs and lets the record through.** Root's log level is WARNING, which drops an INFO record before any handler sees it. stackr's application template sets `portalr.access` and `grantr.audit` to INFO in its `LOG_CONFIG`; an application not generated from it must do the same.
- **A visit to Langfuse or Grafana that doesn't start here, or from a link already copied, is not recorded**, because portalr never sees it.

To read it, query Loki for the application's `portalr.access` records, in Grafana's Explore.

## What an operator can't do from admin

- Open a tenant's admin pages unless they are a member of it (the tenant's owners and admins do). Operators see across tenants through the tools, on the record.
- Delete a tenant, grant or revoke an operator, or create a LiteLLM team. These are grantr's API and `make tenant`.
