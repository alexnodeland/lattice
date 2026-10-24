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
- **The application lives in `.local/run/portal`,** inside the clone, where `.gitignore` keeps it out of lattice's history. It is a repository of its own, as `copier update` and its hooks need. It is generated beside that directory and moved there once whole, so a run that dies leaves nothing half-made in its place; a directory there that `make dev` didn't generate is refused. A render under `.local` locks and syncs as a project of its own, and lattice's workspace also says `exclude = [".local"]`, so it never becomes a member. `DEV_APP_DIR` puts it elsewhere, but never around lattice itself.
- **It is generated once, as the smoke test generates it:** `copier copy --vcs-ref` at lattice's `HEAD`, with no `libraries_path`. Its image installs the libraries from GitHub at that commit. `make dev` fetches origin and refuses a commit that isn't there, before anything starts, and `DEV_REF` names another. An application generated from an older commit is said, with `copier update` as the way to move it.
- **The defaults:**
  - The template's defaults, the portal among them.
  - Every crafting app the template pins except those built for one platform: today Blender, amd64's alone. The list comes from `copier.yml`'s `platform:`, so it doesn't drift.
  - Diagrams on, replay off, and everything bound to `127.0.0.1`.
  - The crafting apps and diagrams are written only while `.env` doesn't choose them, so a choice of your own stays.
- **Secrets stay in files.**
  - The gateway keys are made once, by stackr's `create-tenant` (as `DEV_TENANT`) and `create-portal-key`, each only when the application's `.env` lacks it.
  - Each goes from its script's output into stackr's `scripts/wire-app` on stdin, then into the application's `.env`, mode 0600, as soon as it is made: a later failure doesn't lose it. They are never printed or passed as an argument. A key the gateway has but can't give back stops the run, with how to recover.
  - `scripts/wire-app` gives the `.env` the rest of the stack's settings. Each key has one line, so `make` and Compose read the same value. The smoke test now uses it too.
- **The database role is made with `db-roles` in the application's container before it starts,** as the smoke test does. That, the image's build and the start run every time, and change nothing that is already so. The first person in, which asks for a password, is `make first-run` in the application's directory, and `make dev` says so.
- **Running it again is safe.** It generates the application and makes the keys once.
- **`make dev-down` runs each project's own `make down`, the application's first, which keeps their data.** `make dev-reset` deletes the containers and volumes of exactly the two projects, the application's (as its `compose.yaml` names it, which must be a project name and not `stackr`) and then `stackr`, with `docker compose -p <name> down --volumes`, once you type `yes` in a terminal. It shows the Docker context first, and says that `stackr` is the one stack every clone and worktree on the machine shares. `COMPOSE_PROJECT_NAME` and the other `COMPOSE_*` settings are unset, so neither project is renamed. Nothing else of Docker's is removed.

## Consequences

- One command runs the system as a person would use it, at the clone's committed and pushed code.
- Library changes not yet pushed aren't in the application's image. The smoke test has the same limit.
- `make dev` can't be tested end to end in CI without a second stack. `scripts/check-dev` runs it against fakes, as the root's `check-dev` task: its order, what it refuses before anything starts, its keys kept through a failure, a failed generation, and what `reset` deletes. `scripts/wire-app` is checked by `scripts/check-make`, and the smoke test exercises it on every Smoke job.

## Options considered

- **One Compose project for the stack and the application.** One `up` and one `down`, but the application's `compose.yaml` would have to become part of stackr's, or include it, and the template's application would no longer run beside a stack it doesn't own, as on a single host or another machine's. Not chosen: two projects behind one command keep each as it is.
- **Two projects behind one command.** Chosen: each project's own commands keep working in its directory, and the wiring between them is the one thing added.
- **Building the application from the clone's libraries** (Compose `additional_contexts`). See the follow-up below.

## Follow-up

- **Building from a local checkout.** An optional build context for the libraries (Compose `additional_contexts`) would let the application's image install them from the clone, unpushed changes included. That is a change to every library's install in the template, and needs a decision of its own.
