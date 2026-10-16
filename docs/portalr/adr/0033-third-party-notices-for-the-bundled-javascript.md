# ADR-0033: Third-party notices for the JavaScript the UIs bundle

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Answers [#185](https://github.com/alexnodeland/lattice/issues/185), raised in the review of the Tremor charts: the wheel named the typefaces' licences and Tremor's, and nothing of the packages the two UIs bundle.

## Context

The app and admin UIs are built by Vite into `src/portalr/static/`, and the wheel and the test application's image carry that directory. Their bundles hold React, TanStack Router and Query, Base UI, Recharts and its d3 modules, lucide, Streamdown and the packages those need: 115 in the app's, 140 in admin's. MIT, ISC, BSD, 0BSD and Apache-2.0 all ask that their text, and their NOTICE where they have one, travels with the code. The wheel carried none of it. The Tremor charts' notice (`web/ui/NOTICE`) is hand-written, since it describes a change lattice made; the bundled packages' are not ours to write, nor to keep up by hand.

The user decided the policy: a strict allowlist, JavaScript only, Unlicense on the list.

## Decision

- **Each UI's build writes `THIRD-PARTY-NOTICES.txt` beside its `index.html`,** from the modules its bundle holds, not from the lockfile: a package that is tree-shaken out isn't in it, and one that is added to it is, with no list to keep. `web/notices` is a Vite plugin (`@portalr/notices`) that app and admin use. It reads the bundle's module ids in `generateBundle`, finds each package, and takes its name, version, declared licence, source and every `LICENSE`, `COPYING` and `NOTICE` file at its root, so an Apache-2.0 package's NOTICE is carried. A package that vendors others, such as `victory-vendor`, keeps their licences beside the modules, so the files in the directories above a bundled module count too.
- **The file is generated, never committed or edited,** and is the same for the same bundle: packages in name and version order, line endings normalised, no date. A test holds that the order modules arrive in doesn't change it.
- **It is in the wheel and the image** as part of `static/`. It is not in `license-files`, though that is where the typefaces' licences are: a glob that matches nothing is invalid metadata, and `static/` is built, not committed, so every install that hasn't built the UIs would fail. `ui-in-wheel` checks the wheel instead: each UI's file is there, has an entry for every package with its licence text (or a stated reason it has none), and names a package that UI certainly bundles. The notices are written by the same build that makes the bundle, and a moon build's inputs include the lockfile and the plugin, so it cannot be older than the bundle.
- **The build fails on a package whose licence the policy doesn't allow.** `web/notices/policy.json` holds the allowlist the user chose: 0BSD, Apache-2.0, BSD-2-Clause, BSD-3-Clause, BlueOak-1.0.0, CC0-1.0, ISC, MIT, Python-2.0 and Unlicense. Anything else fails, GPL, AGPL, LGPL and MPL included, and so do a package that declares no licence, one whose field isn't SPDX (`SEE LICENSE IN …`, `UNLICENSED`), and one that ships no licence text.
  - **Expressions are read as SPDX:** `MIT AND ISC` needs both allowed, `(MIT OR GPL-3.0-only)` either, `AND` binds tighter than `OR`, `X+` is as `X`, and a `WITH` exception is never allowed. The legacy `licenses` array is an `OR`.
  - **An exception is a package, the licence it declares and a reason,** in `policy.json`, committed and reviewed. `licence` excuses a licence that isn't allowed, and `text` a package that ships no text. It covers exactly that licence, so a package that changes its licence fails again. One exists: `victory-vendor` (MIT AND ISC) ships no licence file for its shim, which only re-exports the d3 packages, each noticed as an entry of its own.
  - **A stale exception fails,** one whose package isn't in either bundle, declares another licence, or no longer needs it. It is checked by `portalr:licence-exceptions` over both UIs' notices, since an exception one UI needs is not stale because the other doesn't bundle the package.
- **The logic is tested with fixtures** (`web/notices`, run by Vitest in Node): allowed, disallowed, missing, expressions, an exception, a stale exception, vendored licences, NOTICE files, and the file's order. Disallowing ISC in `policy.json` fails the admin build with the 13 packages named.

## Options considered

| Option | For | Against |
|---|---|---|
| **A plugin over the bundle (chosen)** | Exactly what is shipped; one place for the check | Runs under the build |
| A script over `bun.lock` | Simple, no build | Names packages that were tree-shaken out, and misses none of the dev ones either |
| A hand-kept list | None | It drifts |
| Allow copyleft with a notice | Fewer failures | The user chose a strict list |

## Consequences

- Easier: the wheel carries what the licences ask, and a new dependency under a licence nobody has looked at stops the build, with the reason named.
- Easier: nothing to keep up; a lockfile change rebuilds the UIs and the notices with them.
- Harder: a package that ships no licence text needs an exception with a reason, however fine it is.
- The notices are 150 to 180 KB a UI, uncompressed, beside the UIs.
- Not covered: Python dependencies, which the user left out, and the typefaces and Tremor, which keep their own files.
