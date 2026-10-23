# ADR-0040: Scenarios against a generated application, and size budgets

**Status:** Accepted, amended by [ADR-0044](0044-highlighting-and-math-on-demand.md) (an add-on's chunks have a budget of their own) and [ADR-0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md) (the app's total raised to 520 kB, for mini apps)
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

## Context

Phase 7a ([stackr ADR-0038](../../stackr/adr/0038-portalr-in-the-template.md)) made the template mount portalr. Everything that drives the UIs in a browser still ran against portalr's own test application (`tests/app`, [ADR-0013](0013-the-apps-scenarios-against-the-test-application.md)), which has its own world: acme, globex and eight people, a scripted agent, an in-memory grantr and no Supabase of its own. Nothing showed that the application the template generates, with its own Supabase wiring, its own gateway and its own agents, lets a person sign in and work, or shows them by email. Phase 7b of the [plan](../rfcs/0001-v0.1-implementation-plan.md) also promised the Acceptance job's portalr steps, and ADR-0015 left the bundles' size budgets to phase 7.

Two facts bound the design. The browser needs a Supabase Auth it can reach at `<url>/auth/v1`: local Supabase has it on this machine, but GoTrue alone (the PostgreSQL adapter) serves at its root, and a single host's edge is a TLS name the runner can't resolve. And [#172](https://github.com/alexnodeland/lattice/issues/172), [#254](https://github.com/alexnodeland/lattice/issues/254) and [lattice ADR-0002](../../adr/0002-ci-runs-every-affected-project-and-its-dependents.md): Chromium fails every request in flight with `ERR_NETWORK_CHANGED` when any network interface comes or goes, as a container's does.

## Decision

- **A few scenarios, not all of them, run against the application stackr's smoke test starts.** `bdd/generated/` in app and admin holds the features that hold for any generated application: in app, signing in to the owner's tenant, starting a thread in a workspace and reading the agent's answer (the gateway's mocked reply, `stackr smoke ok`), a wrong password refused, signing out; in admin, opening on the tenant, and Access's Members naming the tenant's people by email. The other features stay on the test application: they rely on its seeded world (a scripted agent that asks questions and proposes edits, eight roles, tools that are up and down), which a generated application does not have, and rebuilding it there would test the seeds.
- **The same step definitions, one more feature directory.** `PORTALR_FEATURES` in each Playwright configuration names the features, `bdd/features/*.feature` unless `scripts/generated` sets it, so a step written for the test application serves both and a change to one is run against the other.
- **The smoke test seeds the world and runs them last.** Once its own checks have passed, `smoke_scenarios` makes alice (acme's owner) and bob (a member) in local Supabase, creates acme with the application's own admin command, and makes bob an editor of its workspace `notes` (which is how a workspace becomes one grantr offers), then runs app's and admin's scenarios from `scripts/generated`, which start and stop nothing. The application's `.env` names local Supabase as the portal's project, with its publishable key, and gives the application the secret key, for naming people and inviting; the file is written mode 0600, the key is in no argument, and the browser is given only the publishable one.
- **Local Supabase only, and only where asked.** The leg of the Smoke job that runs the application on local Supabase sets `SMOKE_SCENARIOS=true`, installs Bun's packages and Chromium before the stack starts, and uploads Playwright's traces on failure. A run without it, on another machine or leg, says so and why, and does not pretend. The single host's leg already checks the sign-in call through the edge, in curl, and that Chromium would need the edge's names.
- **Serialised.** The Chromium phase is the last thing the smoke test does with the application: `docker compose run`, which the probes use, makes a container and a network interface, so nothing of the sort runs while it does, and Chromium's install and the packages come before the stack's containers do. The Acceptance job already runs app's and admin's scenarios against the test application, one project after another ([lattice ADR-0002](../../adr/0002-ci-runs-every-affected-project-and-its-dependents.md)); that is the plan's "Acceptance job's portalr steps", and it is unchanged.
- **Size budgets, as ceilings.** `size-budget.json` holds, for each UI, three gzip sizes in bytes: `initial` (the entry, the chunks index.html preloads, the stylesheet), `total` (every script and stylesheet) and `largest` (the largest file, which is Streamdown's chunk, in both). `scripts/check_size.py` reads what the builds wrote and fails over any of them; `moon run portalr:size` is one of `portalr:check`'s dependencies. Each ceiling was set roughly ten percent above the size when it was set, and is raised only in the change that grows past it, which says why, so growth is noticed in the change that causes it. Two sit differently: the app's `total` is about a fifth above its size at the time, and the app's `initial` is raised only with the owner, each time said here: 200 to 202 kB for the brand kit (#524); 202 to 203 kB for the failure text #561 designs (sentences by reason code, and a console line cleaned and redacted, about 0.8 kB) and main's growth before it, measured at 202,098 bytes. It has about 900 bytes of headroom, so its next growth comes with a cut, or a raise the owner agrees. Sizes at the time: app 179 / 425 / 144 kB (initial has since grown to about 200 kB), admin 202 / 604 / 144 kB (initial / total / largest). Ceilings: app 203 / 521 / 160 kB, admin 225 / 670 / 160 kB.
- **Product analytics' capture is an add-on of its own** (`ui/src/on-demand/analytics.ts`, lattice RFC-0008), loaded only once a person says yes: its ceiling is 600 bytes, total and largest, about 550 at the time. Its consent switch and read are in the app's first load. The app's `total` was raised from 520 to 521 kB for product analytics' consent: its read, the switch with its rollback, and the status region, about 1.9 KB that every deployment carries; the first load and the add-on's ceiling are unchanged (lattice RFC-0008, #622).

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Where | **The smoke test's application (chosen)** | A real stack, gateway, Supabase and agents; no second stack to start | Chromium waits for the smoke test's other checks |
| | A job of its own | Isolated | Starts the whole stack again for a few scenarios |
| | The template's own CI | The application's tests run there | It has no stack, no gateway, no Supabase |
| Which | **A tagged few, in their own directory (chosen)** | Each runs and says what a generated application can do | Two feature directories to keep in step |
| | Every feature, seeding the test application's world | One set | The seeds, not the application, would be tested |
| Adapter | **Local Supabase (chosen)** | `/auth/v1` and CORS, as supabase-js expects | The PostgreSQL and single-host legs have no browser scenario |
| | GoTrue behind a path proxy | Every leg | A test-only proxy |
| Budgets | **Ceilings in a file, gzip (chosen)** | Simple, checked on every build, nothing to host | A number to raise by hand |
| | A bundle-size service | Trends | Another account (no external infra) |

## Consequences

- Easier: a change to the template, the router or the UIs that breaks sign-in, the agent's answer or the people's names in a generated application fails the Smoke job; a UI that grows past its budget fails `portalr:check`.
- Harder: the Smoke job on local Supabase installs Chromium and runs two more projects' scenarios, a few minutes more.
- Not covered: the scenarios on the PostgreSQL and single-host legs; the invitation flow, since local Supabase in CI runs without its mail server.
- Phase 7b of [RFC-0001](../rfcs/0001-v0.1-implementation-plan.md) is done.
