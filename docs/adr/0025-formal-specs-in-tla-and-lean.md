# ADR-0025: Formal specs in TLA+ and Lean

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

## Context

Some of the packages' protocols are state machines that several processes run at once, against durable state, and that crash, fail and are cancelled at every await. artifactr's thread claim and turn protocol ([artifactr ADR-0055](../artifactr/adr/0055-turns-from-the-log.md)) is the clearest case: three reviews of its design each found losses and duplicates the one before had missed, and each finding became a regression test. Tests check the interleavings someone thought of. A model checker checks every interleaving within a bound, and shows the shortest trace that breaks a property.

Other logic is pure and total, such as core's command rules: one input, one answer, no interleaving. A model checker adds little there; a proof assistant could prove it correct for every input. That is a larger investment, and nothing needs it yet.

The pilot is artifactr's thread claim: [`docs/artifactr/spec/`](../artifactr/spec/README.md). TLC found four bugs in the code as it is ([#249](https://github.com/alexnodeland/lattice/issues/249), [#250](https://github.com/alexnodeland/lattice/issues/250), [#251](https://github.com/alexnodeland/lattice/issues/251), [#252](https://github.com/alexnodeland/lattice/issues/252)), and confirmed ADR-0045's known hole.

## Decision

- **TLA+, checked with TLC, for state machines with interleavings and crashes:** claims, leases, cursors, hand-overs, retries. A spec models the code as it is, each action a function or an await of it, and says what it leaves out.
- **Lean, later, for pure and total logic,** when a rule's correctness for every input is worth a proof. Not now: no Lean is set up until a package needs it, with its own record.
- **A package's specs live in `docs/<package>/spec/`:** the `.tla` module, its `.cfg` configurations, and a README with a table mapping each action to the code it models, each property to the invariant it checks and its test, and what TLC found.
- **An ADR cites a spec by its property names,** such as "artifactr's `I3_NoStrandedAsk`", and links the spec's README. A record whose decision changes a modelled protocol says whether the spec changed with it.
- **A spec is a small-scope claim, not a proof.** Each configuration sets explicit bounds (two or three processes, two or three messages, one fault), and its README says what they mean. A property that holds is reported as holding at those bounds. A property TLC finds violated is a finding: an issue is filed for each real bug, and the fix is its own pull request, which adds the property to a CI configuration.
- **Drift is caught by names.** Each property is named after the invariant it checks (`I1_...` for I1), and the spec's header table ties it to a test of the package. `scripts/check_spec.py`, which lattice's tests run, fails when a property in the table is undefined, missing from the README, or names a test that doesn't exist; when a configuration checks a property not in the table; or when the package's tests hold an invariant (`test_i3_...`) that no row names, or the spec doesn't say it leaves out. The pull request and ADR templates ask whether a protocol change changed its spec.
- **CI runs TLC only where it matters.** Each package with a spec has a `spec` task, whose inputs are its spec and its source, and CI's `Specs` job runs it in each affected project ([ADR-0002](0002-ci-runs-every-affected-project-and-its-dependents.md)), at the small bounds, within ten minutes ([ADR-0007](0007-a-timeout-on-every-test-and-every-job.md)). The aggregate `CI` check needs it, as it needs every other job. Nightly runs the `spec` and `spec-deep` tasks of every package, at deeper bounds.
- **TLC is the official release's `tla2tools.jar`, by exact version, checked by its SHA-256** before every run (`scripts/tlc`). It is 1.7.4, the latest stable release; 1.8.0 is a prerelease. Its release notes publish the jar's SHA-1, which the downloaded jar matched before its SHA-256 was recorded. A new version is pinned the same way, from a stable release. TLC runs in GitHub Actions; nothing needs installing to work on the rest of lattice.

## Options considered

### Option A: TLA+ with TLC, in the repository, checked in CI (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a spec per protocol, a Java step in one job |
| Finds | Interleavings, crashes and lapses that break safety or liveness, with a trace |
| Drift | Named properties tied to tests, checked by a script, and an affected-only job |

**Pros:** exhaustive within its bounds; traces are readable; TLC is one jar.
**Cons:** the spec is a second description of the code, which drifts unless something holds it; a bound is not a proof.

### Option B: Property-based and stateful tests alone

| Dimension | Assessment |
|---|---|
| Complexity | Low: Hypothesis is already a habit |
| Finds | What random interleavings reach, against the real code |
| Drift | None: they run the code |

**Pros:** no second description. **Cons:** they sample rather than exhaust, and a crash at a given await or a lapse mid-write is hard to inject. They complement a spec rather than replace it.

### Option C: Lean for everything

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Finds | Proofs for all inputs |
| Drift | As for TLA+ |

**Pros:** proofs, not bounds. **Cons:** proving a concurrent protocol is far more work than model-checking it, and the pure logic that suits Lean has no pressing need.

### Option D: Specs outside the repository, run by hand

**Pros:** nothing in CI. **Cons:** they drift silently, and nobody runs them.

## Trade-off analysis

A model checker earns its cost where the reviews kept finding bugs: concurrency, crashes and leases. Keeping the spec in the repository, its names tied to tests and its checks in CI, makes the second description cheap to keep honest, and the affected-only job keeps it from slowing pull requests that don't touch it. Lean waits until a pure rule is worth a proof.

## Consequences

- Easier: a protocol change can be checked against every interleaving at small bounds before it merges, and a finding comes with its trace.
- Easier: an ADR can cite exactly which property a decision preserves.
- Harder: a protocol change carries a spec change, and its author needs to read TLA+.
- Harder: CI depends on a Java runtime and a jar from GitHub's release storage, in one job.
- Revisit: when a package's pure logic needs a proof, set up Lean in its own record; when TLC 1.8 is a stable release, consider moving to it.

## Action items

1. [x] artifactr's thread claim spec, its configurations and README, `scripts/tlc`, `scripts/check_spec.py` and its test, CI's and Nightly's `Specs` jobs, and the checklist lines in the pull request and ADR templates.
2. [ ] Fix [#249](https://github.com/alexnodeland/lattice/issues/249), [#250](https://github.com/alexnodeland/lattice/issues/250), [#251](https://github.com/alexnodeland/lattice/issues/251) and [#252](https://github.com/alexnodeland/lattice/issues/252), each adding its property to a CI configuration.
