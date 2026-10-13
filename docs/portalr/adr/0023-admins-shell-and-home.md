# ADR-0023: admin's shell and Home: its own tenant, every tenant for operators, and a card per read

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Phase 6 builds admin, the UI for a tenant's owners and admins and the deployment's operators (lattice RFC-0002), on the frame [ADR-0021](0021-the-areas-on-the-frame-and-what-admin-needs.md) gave it. Its first part is the shell: signing in, which tenant it shows, the areas a person may use, and Home's cards. The maintainer decided:

- the code the app and admin both need moves into `client`;
- admin's tenant is in its URL, with its own remembered choice;
- Langfuse's and LiteLLM's areas say "isn't configured" in the scenarios;
- Tempo, Loki and Prometheus show real data, from the test application's own telemetry.

grantr's `/checks` answers for a member of the tenant it names, so it can't say whether someone is an operator. portalr's `/deployment/tenants` answers operators alone.

## Decision

- **`client` holds what app and admin share without a framework of their own:**
  - `Signed`, the session, with `authUrl`;
  - `landing` and `adminLanding`, where each opens;
  - `allowedIn` and `workspaceOf`, and `useMe`;
  - `createQueryClient`, the cache whose read refused for no one signed in ends the session.
  - `ui` holds what they share on screen: `Account`, `useAppearance`, `SignIn`, `StatCard`, `TenantSwitcher`, and `Plain` with admin's lockup. Each UI keeps its own routes.
- **app and admin share one session on their one origin,** so signing in to either signs in to both.
- **admin's tenant is in its URL:** `/t/$tenant` for a tenant, `/deployment` for every tenant.
  - Opening one makes it admin's remembered choice, in this browser under its own key, apart from the app's.
  - admin opens on that choice while it is still the person's to make, then on their one tenant, then on every tenant for an operator with none.
  - Otherwise it offers a choice of these, or says there's no access.
- **admin offers the tenants someone owns or administers,** the tenant roles that hold its areas. A tenant someone doesn't administer, opened by its address, says so.
- **One read says who is an operator:** the deployment's tenants, which answers null for anyone it refuses. The same read fills every tenant's Home.
- **The frame's tenant switch** lists the tenants someone administers, and "All tenants" for an operator, a link to `/deployment`.
  - Under "All tenants", only the deployment's areas show.
  - A tenant's areas show where grantr allows their reads. Home is the only one so far; each later area joins the rail as it lands.
- **Home is a card per read, each with its own state.** A card is reading, shows its figure, or says why it has none: its tool isn't answering, with the reason, or isn't configured, or the read couldn't be made. So one tool that is down fails its own card alone. A tenant's Home shows:
  - its members, by people and service principals, from grantr;
  - its workspaces, from artifactr;
  - its feedback over the last week, from Langfuse;
  - about how many turns failed in the last day, from Prometheus, as the failure rate held for each five-minute step;
  - its spend against its budget, from LiteLLM, with "Near budget" from 80% and "Over budget" past it, as ADR-0021's word and shape.
  - Every tenant's Home shows how many tenants there are, and their spend.
- **The test application sends its own telemetry through stackr's Collector,** with stackr's configuration, which copies the libraries' tenant attributes to `tenant.id`. It sends traces to Tempo alone, metrics to Prometheus, and logs to Loki. The Collector publishes nothing; the application reaches it on compose's network, as `OTEL_EXPORTER_OTLP_ENDPOINT` names it. The test application configures telemetry as the template does, with artifactr's `configure_telemetry`.
- **An empty URL leaves Langfuse or LiteLLM unconfigured** in the test application. admin's scenarios run it so; unset, as the API's collection runs it, they are unavailable, as before.
- **admin has its own scenarios,** `admin:bdd`, in their own compose project, with Chromium of its own, so neither UI's scenarios wait on the other's build. They sign in as acme's owner, an editor, a workspace's admin and the deployment's operator. CI's Acceptance job runs them beside the app's, and keeps both UIs' traces of what failed.

## Options considered

| Option | For | Against |
|---|---|---|
| **Shared code in `client`, shared screens in `ui` (chosen)** | No new package; each UI keeps its routes | `client` holds a session and a hook beside its reads |
| A shared package for the UIs' shell | One home for it | A fifth package for a few files |
| Copies in each UI | Each stands alone | Two of each to keep in step |
| **The tenant in admin's URL, with admin's own last choice (chosen)** | A link opens a tenant; the app's choice stays the app's | Two remembered choices, one per UI |
| One choice shared with the app | One to remember | Choosing in one moves the other |
| **The deployment's tenants as the operator's read (chosen)** | One read for both; nothing new in grantr | A refused read stands for "not an operator" |
| A check grantr answers outside any tenant | Says what it means | A change to grantr's `/checks` |

## Consequences

- Easier: each of phase 6's areas is a route under `/t/$tenant` or `/deployment`, with a nav link where grantr allows it.
- Easier: admin's scenarios read the application's real telemetry, which 6d's Traces and logs scenarios show.
- Harder: a counter's first increase doesn't show in a rate, so "Failed turns" counts from a failure's second sample on.
