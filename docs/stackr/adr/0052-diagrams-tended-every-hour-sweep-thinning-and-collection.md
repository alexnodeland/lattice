# ADR-0052: Diagrams tended every hour: the sweep, thinning and collection

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

## Context

- **artifactr ships the jobs but runs none of them.** It has the tombstone sweep ([artifactr ADR-0091](../../artifactr/adr/0091-diagrams-tombstones-swept-and-their-revisions-thinned.md)), revision thinning ([artifactr ADR-0094](../../artifactr/adr/0094-diagrams-revisions-thinned-to-one-an-actor-every-ten-minutes.md)), and native files' collection of the bytes nothing names ([artifactr ADR-0092](../../artifactr/adr/0092-a-diagrams-images-uploaded-by-a-person-and-read-where-it-names-them.md)). Each is said to run "on a schedule of the application's own".
- **The template scheduled none of them.** A diagram at its limit couldn't shrink, its revisions grew without end, and images uploaded but never named stayed.
- **The application can't list every workspace.** artifactr's storage lists a tenant's workspaces, but with `access: none` the application has no list of tenants either.

## Decision

- **With native files in the template (`use_files`), `Files` tends workspaces as the application starts, then about every hour.** The interval is drawn at random between half and one and a half of `TEND_EVERY`, as the analytics relay spaces its passes, and a pass runs before the first wait, as the relay's does.
- **Which workspaces:** each one a person opened in this process in the last three days (`TENDED`), noted by the libraries' `on_open` hook. A workspace no one opens has no new revisions to thin, no new tombstones and no new bytes; one opened again is tended again. Three days is long enough for a tombstone a day old to be swept, and revisions a day old thinned.
  - Tending opens each workspace itself, which calls the same hook. A context variable set while tending makes the hook pass its own opens over, while a person's request, in a context of its own, is still noted; so tending never keeps a workspace tended, and one no person opens for three days is dropped. Each workspace's time is read as it is reached, not from the pass's start.
- **What tending does, as `TENDER`, an actor that sees everything** (the sweep's own, `SWEEPER`, with diagrams):
  1. with diagrams (`use_diagrams`), sweeps tombstones a day old;
  2. with diagrams, thins revisions a day old (on the storage, with the integration's switch);
  3. while a native files' app runs, collects the bytes nothing names. That closes the gap ADR-0091 and ADR-0092 assumed was filled, with diagrams or without.
- **A workspace that fails** is left for the next tending, and the rest are tended. The log says its id and the error's type alone, at warning: an error's message may quote what the workspace holds.
- **A tending that fails as a whole** is said in the log with its traceback, and the loop carries on, as the analytics relay's does: a failure never stops tending for the life of the process.
- **Each process tends the workspaces it opened.** Two that tend one workspace do the same work. Thinning is idempotent, and a sweep that loses to another's commit is skipped as a diagram changed meanwhile, so no lease is taken.
- `Files.tend_once()` is the tending itself, for tests and an operator. The lifespan runs it in a loop and stops it with the application.

## Consequences

- A generated application with native files collects, and with diagrams also sweeps and thins, with nothing to configure.
- CI's template matrix runs the native-files-only variant too (`TEMPLATE_DIAGRAMS=false`).
- A process restarted has no opened workspaces: its first pass tends nothing, and the first useful one follows a person's first open.

## Alternatives considered

- **A cron job or a separate service:** rejected. It is one more thing to deploy for a few database reads an hour, and stackr's default runs one process.
- **Every workspace of every tenant from storage:** rejected for now. It needs a list of tenants the application doesn't have under `access: none`, and it would tend workspaces no one uses.
