# ADR-0033: Third-party notices for the JavaScript the UIs bundle

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Answers [#185](https://github.com/alexnodeland/lattice/issues/185), raised in the review of the Tremor charts: the wheel named the typefaces' licences and Tremor's, and nothing of the packages the two UIs bundle.

## Context

The app and admin UIs are built by Vite into `src/portalr/static/`, and the wheel and the test application's image carry that directory. Their bundles hold React, TanStack Router and Query, Base UI, Recharts and its d3 modules, lucide, Streamdown, Tailwind's styles and the packages those need: 113 packages in the app's, 138 in admin's. MIT, ISC, BSD, 0BSD and Apache-2.0 all ask that their text, and their NOTICE where they have one, travels with the code. The wheel carried none of it. The Tremor charts' notice (`web/ui/NOTICE`) is hand-written, since it describes a change lattice made; the bundled packages' are not ours to write, nor to keep up by hand.

The user decided the policy: a strict allowlist, JavaScript only, Unlicense on the list.

## Decision

- **Each UI's build writes `THIRD-PARTY-NOTICES.txt` beside its `index.html`,** from the modules its bundle holds, not from the lockfile: a package that is tree-shaken out isn't in it, and one that is added to it is, with no list to keep. `web/notices` is a Vite plugin (`@portalr/notices`) that app and admin use. It reads the bundle's module ids in `generateBundle`, finds each package, and takes its name, version, declared licence, source, and every notice file at its root: `LICENSE`, `LICENCE`, `LICENSES`, `COPYING`, `COPYRIGHT`, `UNLICENSE` and `NOTICE`, bare, with `.md`, `.txt` or `.rst`, or as `LICENSE-MIT`. A source file named like one (`license.js`, `notice.ts`) is not. An Apache-2.0 package's NOTICE is carried with its licence.
  - **Stylesheets are read as written.** The bundler's module list holds JavaScript and the stylesheets imported from it, but not what a stylesheet pulls in itself: `@import "tailwindcss"` puts Tailwind's CSS in the UI's styles, and the module list never names Tailwind. The plugin reads each stylesheet of the bundle from disk, before Tailwind has inlined its imports, and follows `@import`s of packages, and of relative files, for the packages they name.
  - **A package that can't be named fails the build.** Code from a `node_modules` directory with no `package.json`, or one with no name and version, throws, rather than going unnoticed.
- **The file is generated, never committed or edited,** and is the same for the same bundle: packages in name and version order, line endings normalised, no date. A test holds that the order modules arrive in doesn't change it.
- **It is in the wheel and the image** as part of `static/`. `ui-in-wheel` checks the wheel: each UI's file is there; every entry has a heading of the form `## name@version` and a `LICENSE` or `COPYING` text (a `NOTICE` alone is not one) or a stated reason it has none; and `react`, which both bundle, is named. The notices are written by the same build that makes the bundle, and a build's cache cannot outlive the lockfile: `.moon/tasks/typescript.yml` makes `/bun.lock` an input of every web task, a test holds that app's and admin's builds add to those inputs and don't replace them, and they add the plugin's sources and `policy.json`. A transitive bump changes `bun.lock`, so rebuilds.
- **The build fails on a package whose licence the policy doesn't allow.** `web/notices/policy.json` holds the allowlist the user chose: 0BSD, Apache-2.0, BSD-2-Clause, BSD-3-Clause, BlueOak-1.0.0, CC0-1.0, ISC, MIT, Python-2.0 and Unlicense. Anything else fails, GPL, AGPL, LGPL and MPL included, and so do a package that declares no licence, one whose field isn't SPDX (`SEE LICENSE IN …`, `UNLICENSED`), and one that ships no licence text.
  - **Expressions are read as SPDX:** `MIT AND ISC` needs both allowed, `(MIT OR GPL-3.0-only)` either, `AND` binds tighter than `OR`, `X+` is as `X`, and a `WITH` exception is never allowed. The legacy `licenses` array is an `OR`.
  - **An `OR` with a disallowed alternative is fine when one side is allowed,** as SPDX has the one who uses a package choose. The entry records the choice, `Used under: MIT` after its `Licence:` line, which is the first allowed alternative of the expression, and a test holds it.
  - **An exception is a package, the licence it declares and a reason,** in `policy.json`, committed and reviewed. `licence` excuses a licence that isn't allowed, and `text` a package that ships no licence text. It covers exactly that licence, so a package that changes its licence fails again, and any version of the package: it is not tied to the one that was reviewed. A reason that isn't text, or the same exception twice, is refused. One exists: `victory-vendor` (MIT AND ISC) ships no licence file for its shim, which only re-exports the d3 packages, each noticed as an entry of its own.
  - **A stale exception fails,** one whose package isn't in either bundle, declares another licence, or no longer needs it. It is checked by `portalr:licence-exceptions` over both UIs' notices, since an exception one UI needs is not stale because the other doesn't bundle the package.
- **The wheel's `license` expression names the licences the bundles are under.** It lists lattice's own (MIT, the typefaces' OFL-1.1, Tremor's Apache-2.0) and each SPDX identifier the bundled packages are used under: for an `OR`, the one elected. `portalr:licence-expression` compares it with the generated notices and fails when a bundled identifier is missing from it, or it lists one nothing bundled is under.
- **The notices file can't be mistaken by its own format.** An entry ends at the separator line followed by a `## ` heading; a licence text that holds both fails the build, and a text holding the separator alone stays in its entry.
- **The logic is tested with fixtures** (`web/notices`, run by Vitest in Node): allowed, disallowed, missing, expressions, an election, an exception, a stale exception, NOTICE files, file names, the order and the format. The plugin is run in a real `vite build` of a small project: a used package is in the notices, a fully tree-shaken `sideEffects: false` package is not (the bundler leaves it out of its module list, so no filter was needed), a package of CSS alone and one only a stylesheet imports are, and a disallowed package fails the build. Disallowing ISC in `policy.json` fails the admin build with the 13 packages named.

## Options considered

| Option | For | Against |
|---|---|---|
| **A plugin over the bundle (chosen)** | Exactly what is shipped; one place for the check | Runs under the build |
| A script over `bun.lock` | Simple, no build | Includes devDependencies and packages that were tree-shaken out |
| A hand-kept list | None | It drifts |
| Allow copyleft with a notice | Fewer failures | The user chose a strict list |

## Consequences

- Easier: the wheel carries what the licences ask, and a new dependency under a licence nobody has looked at stops the build, with the reason named.
- Easier: nothing to keep up; a lockfile change rebuilds the UIs and the notices with them.
- Harder: a package that ships no licence text needs an exception with a reason, however fine it is.
- The notices are 150 to 180 KB a UI, uncompressed, beside the UIs.
- **A gap: the notices are not in `dist-info/licenses`,** where scanners and licence tools look for a wheel's licences. `uv_build` rejects a `license-files` glob that matches nothing, so a path under the built `static/` can't be listed without breaking every install that hasn't built the UIs, and it can't include a generated file otherwise. The notices are in the wheel at `portalr/static/<ui>/THIRD-PARTY-NOTICES.txt`, and the `license` expression names their licences, but a tool that reads only `dist-info/licenses` won't see them. Closing it needs a build backend that can include generated files, or a step after the wheel is built.
- The counts of 113 and 138 are the packages in each bundle; they were checked against the lockfile's runtime closure of the four web packages (189 packages), of which the bundles leave out workspace packages, `@types` packages and code that is tree-shaken out, and add only `tailwindcss`, a devDependency whose CSS is copied into the styles.
- Not covered: Python dependencies, which the user left out, and the typefaces and Tremor, which keep their own files.
