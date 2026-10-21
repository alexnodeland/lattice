# ADR-0058: A new version offered to a stale tab

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

A tab opened before a deploy keeps running the build it loaded. The owner opened a thread in such a tab after mini apps had shipped and saw nothing of the app the agent made: the old build had no inline entry for it. Nothing told them to reload.

## Decision

- **A UI's build is its page's entry script.** Vite names it by its content's hash (`<base>assets/index-<hash>.js`), so the page the UI is served as names its build, with no version to keep in step. The tab's own entry is read from its document; the served page is read again with `no-store` every five minutes and whenever the tab is shown again (`visibilitychange`). Only an answer that is ok, not redirected and HTML, whose entry is under the UI's own `assets/`, names a build: a sign-in page, a captive portal or a failing server never does. In development the entry is the source (`src/main.tsx`), under no `assets/`, so nothing is compared.
- **A build is new once it is read twice running,** so a rolling deploy or a rollback that flaps between two builds is never offered mid-flight.
- **The person chooses.** `NewVersionOffer` keeps an empty polite live region (`aria-live`, not a `status`, so the page's own statuses stay the only ones) on a built page from its first render, so what appears in it is announced; a new build puts `NewVersion` in it: "A new version of portalr is ready. Reload to use it." ("portalr admin" in the admin, the name the shell's mark has), with "Not now" and "Reload", keyboard buttons, without motion. It sits below a narrow window's bar and the skip link, and lets clicks through where it draws nothing. "Not now" holds for that build in that UI, kept in the browser's storage under the UI's address and heard by its other tabs; a later build is offered again.
- **Nothing reloads by itself.** "Reload" is the person's, and the page's own guards still apply: the native file editor's unsaved-changes guard (`beforeunload`) asks before it is lost. A form without such a guard loses what was typed in it, as any reload does.

## Consequences

- Easier: a tab that outlived a deploy says so within five minutes, or as soon as it is looked at again.
- Harder: each open tab reads its UI's page every five minutes, a few kilobytes, and on each return to it.
