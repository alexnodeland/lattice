# ADR-0023: admin's shell and Home: its own tenant, every tenant for operators, and a card per read

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Phase 6 builds admin, the UI for a tenant's owners and admins and the deployment's operators (lattice RFC-0002), on the frame [ADR-0021](0021-the-areas-on-the-frame-and-what-admin-needs.md) gave it. Its first part is the shell: signing in, which tenant it shows, the areas a person may use, and Home's cards. The maintainer decided:

- the code the app and admin both need moves into `client`;
- admin's tenant is in its URL, and admin remembers the last one in this browser;
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
  - Opening one, or switching to it, makes it admin's remembered choice, in this browser. The app remembers none: its URL alone says where a person is.
  - admin opens on that choice while it is still the person's to make, then on their one tenant, then on every tenant for an operator with none.
  - Otherwise it offers a choice of these, or says there's no access.
- **admin offers the tenants someone owns or administers,** the tenant roles that hold its areas. A tenant someone doesn't administer, opened by its address, says so.
- **One read says who is an operator:** the deployment's tenants, which answers null where portalr or grantr refuses it as `forbidden`, and fails otherwise. It is kept by the person it was read for, for a minute. The same read fills the deployment's Home. A tenant's frame reads it only for the switch, so a tenant's admin never waits on it.
- **Who may open a tenant, or every tenant, is settled before any of its routes load,** in `beforeLoad`, so no area's read goes out first.
- **The frame's tenant switch** lists the tenants someone administers, and "All tenants" for an operator, a link to `/deployment`.
  - Under "All tenants", only the deployment's areas show.
  - A tenant's areas show where grantr allows their reads. Home is the only one so far; each later area joins the rail as it lands.
- **Home is a card per read, each with its own state,** read with suspense under a boundary of its own. A card is reading, and busy; shows its figure; or says why it has none, with a shape and a word: its tool isn't answering, with the reason, or isn't configured, or the read failed. A read refused because the reader may not hides its card. So one tool that is down fails its own card alone. Each card's words are derived in one module from its read's generated type, and tested there. A tenant's Home shows:
  - its members, by people and service principals, from grantr;
  - the workspaces with a log they can open in artifactr;
  - people's feedback over the last week, from Langfuse: the scores no evaluator gave, as evalr's metadata says, and of the yes-or-no ones, how many said yes. A figure at the read's limit shows as at least it, "1,000+";
  - its failed turns in the last day, from Prometheus: the increase over the day of artifactr's failed turns, which artifactr starts at zero as a turn starts, so a first failure counts too ([artifactr ADR-0067](../../artifactr/adr/0067-a-failed-turns-series-starts-at-zero.md));
  - its spend against its budget, from LiteLLM, with its period in words, and "Near budget" from 80% and "Over budget" past it, as ADR-0021's word and shape.
  - Every tenant's Home shows how many tenants there are, and their spend.
- **portalr's Prometheus metric `failed_runs` becomes `failed_turns`:** each point counts the failed turns in the step before it, from artifactr's turns counter, whose labels are known as a turn starts. Its runs counter names a failure's reason, which isn't. portalr's Langfuse reader names each score's evaluator, from evalr's metadata, and none for a person's feedback.
- **The test application sends its own telemetry through stackr's Collector,** with stackr's configuration, which copies the libraries' tenant attributes to `tenant.id`. It sends traces to Tempo alone, metrics to Prometheus each second, and logs to Loki. The Collector publishes nothing; the application reaches it on compose's network, as a non-empty `OTEL_EXPORTER_OTLP_ENDPOINT` names it. The test application configures telemetry as the template does, with artifactr's `configure_telemetry`, instrumenting FastAPI alone, and leaving compose's health check out: its own HTTP calls are portalr's reads of the tools. Its scripted agent fails a turn when asked to, so a scenario can count one.
- **An empty URL leaves Langfuse or LiteLLM unconfigured** in the test application. admin's scenarios run it so; unset, as the API's collection runs it, they are unavailable, as before.
- **admin has its own scenarios,** `admin:bdd`, in their own compose project, so neither UI's scenarios wait on the other's build; `ui`'s one task installs Chromium for both, so they never install it at once. They share the app's people and their sign-in. They sign in as acme's owner, an admin of both tenants, an editor, a workspace's admin and the deployment's operator. One scenario has a turn fail and reads it back on Home, through the Collector and Prometheus. CI's Acceptance job runs them beside the app's, and keeps both UIs' traces of what failed.

## Options considered

| Option | For | Against |
|---|---|---|
| **Shared code in `client`, shared screens in `ui` (chosen)** | No new package; each UI keeps its routes | `client` holds a session and a hook beside its reads |
| A shared package for the UIs' shell | One home for it | A fifth package for a few files |
| Copies in each UI | Each stands alone | Two of each to keep in step |
| **The tenant in admin's URL, with its last choice remembered (chosen)** | A link opens a tenant; admin opens where the admin was | One more thing kept in the browser |
| The URL alone, as the app has it | Nothing kept | admin opens on a choice each time for an admin of several tenants |
| **The deployment's tenants as the operator's read (chosen)** | One read for both; nothing new in grantr | A refused read stands for "not an operator" |
| A check grantr answers outside any tenant | Says what it means | A change to grantr's `/checks` |

## Consequences

- Easier: each of phase 6's areas is a route under `/t/$tenant` or `/deployment`, with a nav link where grantr allows it.
- Easier: admin's scenarios read the application's real telemetry, which 6d's Traces and logs scenarios show.
- Harder: artifactr's zero for a failed series must be exported before the turn fails, so a failure in the very first turn of a tenant, a workspace and a trigger, before any export, isn't counted.
