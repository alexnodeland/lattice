# ADR-0011: A gate for each app, in place of WordCraft's two releases

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland
**Amends:** [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md#phases), whose gate held every other app back on WordCraft

## Context

RFC-0003 says: "Before a second app, WordCraft's matrix has held for two releases, no hostile file has escaped, the second app's licence is read, and its adapter needs no change to `App`, `Blobs` or `NativeFile`." WordCraft 0.7.0 was three days old when the work on twelve more apps began, and one app's record says little of another's: each has its own CLI, formats and release cadence ([ADR-0009](0009-each-crafting-app-declared-once-on-one-of-two-dialects.md)). Each app is an integration of its own, `files:<app>`, so each can be held back on its own.

## Decision

- **Work on every app goes ahead at once.** No app waits on another's record.
- **An app's key is on by default, or recommended on to a deployment, only once it passes its own gate:**
  1. Its release is pinned, in `scripts/crafts/<app>.sha256`, and its descriptor in `CRAFTS` is what that release offers.
  2. Its fidelity matrix is green in Nightly: every feature of its corpus kept, or failing only where the corpus says the release doesn't keep it, and saving twice a fixpoint.
  3. Its hostile corpus passes: every hostile file ends in a typed `AppFailed` within its deadline. Every app is given an empty file, noise, and a corpus file cut in half; each format adds its own, such as WordCraft's document that inflates to 300 MiB, which its CLI refuses by the size the zip declares, and its content types that aren't XML. Running out the deadline doesn't count: a hostile file is refused, not waited out.
  4. Its CLI confines what it reads and writes, or the sandboxed worker runs it: an app whose CLI confines nothing stays off, and runs only with `trusted=True`.
  5. Its licence and notices are read, and its descriptor's `notices` say what travels with its CLI.
- **A test holds what it can of the gate:** an app on by default has a corpus, with hostile files of its format's own, and so a Nightly run. That the run is green is Nightly's to show, and the pull request that turns a key on links it.
- **Two releases are no longer required,** for WordCraft or any other: a green matrix on the pinned release, and on each release a pin is raised to, is the record. WordCraft passes the gate on 0.7.0: its matrix is green, its hostile files are each refused (an empty file, noise and a cut file as not a zip, the bomb as past its limit, the bad content types as not XML), and its CLI takes a read and a write root.

## Options considered

### Option A: A gate for each app (chosen)

| Dimension | Assessment |
|---|---|
| Fit | Each app is switched on its own, so it is held back on its own |
| Evidence | Its own matrix, its own hostile files, its own confinement |

### Option B: RFC-0003's gate, as written

**Cons:** twelve apps wait on one app's release cadence, which says nothing about them.

### Option C: No gate; each deployment decides

**Cons:** a key on by default is lattice's recommendation, which needs lattice's evidence.

## Trade-off analysis

The gate keeps what RFC-0003's asked of the second app, its licence and its fit to the ports, and asks it of each app, of its own release, instead of asking one app to wait for another's.

## Consequences

- Easier: each app's work lands as it is ready, its key off until it passes.
- Harder: each app needs its own corpus, hostile files and Nightly run before its key is on.
- Revisit: the gate's fourth point, once the worker exists and runs every app.

## Action items

1. [x] Hostile files in the fidelity harness, and the test that an app on by default has a corpus.
2. [ ] Each app's corpus and its own hostile files, by its own work.
