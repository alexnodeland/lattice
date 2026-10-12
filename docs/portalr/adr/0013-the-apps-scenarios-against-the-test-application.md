# ADR-0013: The app's scenarios, against the test application with Supabase Auth

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 makes each area of the app pass a `bdd` scenario, run through playwright-bdd against a running stack, and phase 5 exits when they do. A scenario signs in through Supabase Auth, then asks grantr which tenants and workspaces the person has, and later artifactr and reflexr for the rest. The template only gains a portal in phase 7, so phase 5 has no generated application to run against. Local Supabase, which stackr's Smoke job runs, is a dozen containers, most of which a scenario doesn't touch. portalr ADR-0008 runs the Bun workspace in Bun; playwright-bdd and Playwright's test runner are written for Node.

## Decision

`moon run app:bdd` (`web/app/scripts/bdd`) runs the app's features against portalr's test application ([ADR-0012](0012-acceptance-against-a-two-tenant-stack.md)), extended for them, in a compose project of its own.

- **Supabase Auth is GoTrue, alone,** `supabase/gotrue:v2.197.0`, with a PostgreSQL 17 of its own, set up as GoTrue's own development database is (`tests/app/auth.sql`), in compose's `bdd` profile. It confirms people at once, so the script signs them up without mail, and signs HS256 tokens with a secret the test application shares.
- **It answers at `/auth/v1` on the application's origin,** as it does behind Supabase's gateway: the test application forwards that path to GoTrue, which serves at its root. So `config.json`'s Supabase URL is `/`, a path on the application's own origin, which the app resolves; a deployment names its project's URL as before.
- **The test application verifies the tokens** as the template does, with PyJWT, and takes a person's user id from their email's local part, so its seed needn't know the ids Supabase Auth gives them. A request without a token is still named by `x-user`, for the API tests.
- **It mounts grantr's router** for `/me` and `/checks`, and names artifactr's actions to grantr, which lists a tenant's workspaces by its libraries' `:open` actions. Its seed adds the people the scenarios need: bob and erin, editors of acme's workspaces, erin a member of globex too, and frank, who is in no tenant. artifactr's and reflexr's routers join it with the areas that read them.
- **playwright-bdd runs in Bun,** `bun x --bun`, like every other tool in the workspace: it does, so ADR-0008 stands and no Node is pinned. One feature per area, in `web/app/bdd/features/`, with their steps in `bdd/steps/`.
- **CI's Acceptance job runs the affected `bdd` tasks,** after the `api` ones, with Chromium installed as the Check job installs it.
- **Phase 7 moves the scenarios to an application the template generates,** with the portal, and deletes this wiring of grantr and Supabase Auth from the test application then.

## Options considered

| Option | For | Against |
|---|---|---|
| **The test application with GoTrue alone (chosen)** | Two containers more than the API tests'; real tokens, signed in through the UI | A second wiring of grantr to keep in step with the template's until phase 7 |
| Local Supabase, as the Smoke job runs it | The real gateway and every service | A dozen containers, and the Supabase CLI, for one service the scenarios use |
| A template-generated application | What ships | The template has no portal until phase 7 |
| Running playwright-bdd under Node | Its supported runtime | A second runtime, which ADR-0008 avoided; Bun runs it |

## Consequences

- Easier: a scenario signs in as a person would, and grantr answers it as it would in production.
- Harder: `app:bdd` needs Docker and Chromium, and builds the test application's image.
- Harder: until phase 7, the test application wires grantr and verifies tokens itself, and the two must agree with the template's.
