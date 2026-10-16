# ADR-0025: Formal specs in TLA+ and Lean

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

## Context

Some of the packages' protocols are state machines that several processes run at once, against durable state, and that crash, fail and are cancelled at every await. artifactr's thread claim and turn protocol ([artifactr ADR-0055](../artifactr/adr/0055-turns-from-the-log.md)) is the clearest case: three reviews of its design each found losses and duplicates the one before had missed, and each finding became a regression test. Tests check the interleavings someone thought of. A model checker checks every interleaving within a bound, and shows the shortest trace that breaks a property.

Other logic is pure and total, such as core's command rules: one input, one answer, no interleaving. A model checker adds little there; a proof assistant could prove it correct for every input. That is a larger investment, and nothing needs it yet.

The pilot is artifactr's thread claim: [`docs/artifactr/spec/`](../artifactr/spec/README.md). Its README records what TLC found in the code as it is, and the issues filed for it.

## Decision

- **TLA+, checked with TLC, for state machines with interleavings and crashes:** claims, leases, cursors, hand-overs, retries. A spec models the code as it is, each action a function or an await of it, and says what it leaves out.
- **Lean, later, for pure and total logic,** when a rule's correctness for every input is worth a proof. Not now: no Lean is set up until a package needs it, with its own record.
- **A package's specs live in `docs/<package>/spec/`:** the `.tla` module, its `.cfg` configurations, and a README with a table mapping each action to the code it models, each property to the invariant it checks and its test, and what TLC found.
- **An ADR cites a spec by its property names,** such as "artifactr's `I3_NoStrandedAsk`", and links the spec's README. A record whose decision changes a modelled protocol says whether the spec changed with it.
- **A spec is a small-scope claim, not a proof.** Each configuration sets explicit bounds (two or three processes, two or three messages, one fault), and its README says what they mean, what the spec assumes and what it leaves out. A property that holds is reported as holding at those bounds, and the README shows that each check can fail: a change to the spec that breaks it, and a witness that the behaviours it is checked over are reached. A property TLC finds violated is a finding: an issue is filed for it, as a bug or for a decision, and a test runs its trace against the code, marked as a strict `xfail`. The fix is its own pull request, which takes the mark off and adds the property to a CI configuration.
- **Drift is caught by names.** Each property is named after the invariant it checks (`I1_...` for I1), and the spec's header table ties it to a test of the package for the same invariant. `scripts/check_spec.py`, which lattice's tests run, fails when a property in the table is undefined, missing from the README or checked by no configuration; when its test doesn't exist, or is for another invariant; when a configuration checks a property not in the table, or no task runs the configuration; when the package's tests hold an invariant (`test_i3_...`) that no row names, or the spec doesn't say it leaves out; and when the README's action table names an action the spec doesn't define, or a function the package doesn't. The pull request and ADR templates ask whether a protocol change changed its spec.
- **CI runs TLC only where it matters.** Each package with a spec has a `spec` task, whose inputs are its spec and its source, and CI's `Specs` job runs it in each affected project ([ADR-0002](0002-ci-runs-every-affected-project-and-its-dependents.md)), at the small bounds, within ten minutes ([ADR-0007](0007-a-timeout-on-every-test-and-every-job.md)). The aggregate `CI` check needs it, as it needs every other job. Nightly runs the `spec` and `spec-deep` tasks of every package, at deeper bounds.
- **TLC is the official release's `tla2tools.jar`, by exact version, checked by its SHA-256** before every run (`scripts/tlc`, against `scripts/tlc.sha256`). The pin is trust on first use: GitHub gives no digest for the asset, so the SHA-256 is of the first download, cross-checked against the SHA-1 the release notes publish. A new version is pinned the same way, from a stable release, not a prerelease. TLC runs in GitHub Actions; nothing needs installing to work on the rest of lattice.

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
- Revisit: when a package's pure logic needs a proof, set up Lean in its own record; when a newer TLC is a stable release, consider moving to it.

## Action items

1. [x] artifactr's thread claim spec, its configurations and README, a test against the code for each bug it found, `scripts/tlc`, `scripts/check_spec.py` and their tests, CI's and Nightly's `Specs` jobs, and the prompts in the pull request and ADR templates.
2. [ ] Fix, or decide, each finding the spec's README lists, each fix adding its property to a CI configuration and taking the `xfail` off its test.
