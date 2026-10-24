# ADR-0053: Run everything together

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

## Context

Running the whole system on one machine took two `make up`s and secrets copied by hand. The generated application is a Compose project of its own (`name:` its slug) beside stackr's `stackr` project. It reaches the stack by the external networks `stackr`, `supabase_network_stackr-supabase` and `stackr-umami`. Its `.env` needs:

- Langfuse's keys;
- the database's addresses and owner;
- GoTrue's issuer, keys and admin API on the postgres adapter;
- two gateway keys;
- analytics' and Umami's passwords.

Only the smoke test's `make smoke-app` did all of this, and only for itself.

## Decision

**One command, `make dev`, at lattice's root, keeps the two Compose projects** and does the wiring between them. `make dev-down`, `make dev-status` and `make dev-reset` go with it. `scripts/dev` holds the steps, and `make` only calls it, so no recipe line shows a key.

- **The stack runs on the postgres adapter, with GoTrue,** and with `observability langfuse gateway auth analytics umami`. Umami runs on that adapter alone. A stackr with no `.env` is given `STACKR_DATABASE=postgres`. One whose `.env` chooses local Supabase is refused, not switched, since that is a running stack's.
- **The application lives in `.local/run/portal`,** inside the clone, where `.gitignore` keeps it out of lattice's history. It is a repository of its own, as `copier update` and its hooks need. uv takes it as a project of its own, with its own lock and environment, so lattice's workspace needs no `exclude`. `DEV_APP_DIR` puts it elsewhere.
- **It is generated once, as the smoke test generates it:** `copier copy --vcs-ref` at lattice's `HEAD`, with no `libraries_path`. Its image installs the libraries from GitHub at that commit. `make dev` refuses a commit that isn't on origin, and `DEV_REF` names another.
- **The defaults:**
  - The template's defaults, the portal among them.
  - Every crafting app the template pins except those built for one platform: today Blender, amd64's alone. The list comes from `copier.yml`'s `platform:`, so it doesn't drift.
  - Diagrams on, replay off, and everything bound to `127.0.0.1`.
- **Secrets stay in files.**
  - The gateway keys are made once, `make tenant` (as `DEV_TENANT`) and `make portal-key`, each only when the application's `.env` lacks it.
  - They go from the scripts' output into stackr's `scripts/wire-app` on stdin, then into the application's `.env`, mode 0600. They are never printed or passed as an argument.
  - `scripts/wire-app` gives the `.env` the rest of the stack's settings. Each key has one line, so `make` and Compose read the same value. The smoke test now uses it too.
- **The database role is created before the application first starts,** with `db-roles` in its container, as the smoke test does. The first person in, which asks for a password, is `make first-run` in the application's directory, and `make dev` says so.
- **Running it again is safe.** It renders, makes keys and creates the role once, and starts what isn't running.
- **`make dev-down` runs each project's own `make down`, which keeps their data.** `make dev-reset` deletes the containers and volumes of exactly the two projects, `stackr` and the application's (as its `compose.yaml` names it), with `docker compose -p <name> down --volumes`, once confirmed in a terminal. Nothing else of Docker's is removed.

## Consequences

- One command runs the system as a person would use it, at the clone's committed and pushed code.
- Library changes not yet pushed aren't in the application's image. The smoke test has the same limit.
- `make dev` can't be tested end to end in CI without a second stack. `scripts/wire-app` is checked by `scripts/check-make`, and the smoke test exercises it on every Smoke job.

## Follow-up

- **Building from a local checkout.** An optional build context for the libraries (Compose `additional_contexts`) would let the application's image install them from the clone, unpushed changes included. That is a change to every library's install in the template, and needs a decision of its own.
