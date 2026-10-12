# ADR-0009: `ui` tested in Chromium, in both schemes, under Bun

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md#ui) has `ui` tested in a browser, with Vitest's browser mode and Playwright, in light and dark, and its phase 2 ends when `ui`'s components pass those tests. [ADR-0008](0008-the-bun-workspace-runs-in-bun.md) runs every tool in Bun's runtime and left one thing to prove: that browser mode works there, or Node.js joins `.prototools`.

Phase 2 also brings `ui`'s tokens, from portalr's brand ([lattice ADR-0014](../../adr/0014-portalrs-and-grantrs-marks.md)), and its first primitives.

## Decision

- **Browser mode works in Bun.** `bun x --bun --no-install vitest run` drives Chromium through `@vitest/browser-playwright`, with no Node.js on the path, locally and in CI. Node.js stays out of `.prototools`.
- **Every test runs twice,** in two Chromium instances, `light` and `dark`, whose Playwright contexts set the system's colour scheme. A test reads the scheme it runs in from `matchMedia`.
- **The tests check what the scheme decides:** each component's computed colours against the tokens, and the WCAG contrast of its text, at least 4.5:1, as well as its behaviour, such as a disabled button that can't be pressed.
- **No screenshots yet.** Vitest's screenshot baselines differ by platform, and contributors run macOS while CI runs Linux. Screenshots come when there is a component whose look a computed style can't pin, with baselines made in CI.
- **The tokens are CSS custom properties,** `--portalr-*`, in `tokens.css`: light by default, dark when the system prefers it unless a page sets `data-theme="light"`, and dark whenever it sets `data-theme="dark"`. `styles.css` imports Tailwind 4 and hands the tokens to `@theme inline`, so `bg-accent` follows the scheme.
- **The first primitives are Base UI's `Button` and `Switch`,** styled with the tokens in the shape of shadcn's copied components: a primary button in the working colour, a secondary one on the surface, and a switch whose track takes the working colour.
- **Chromium is Playwright's headless shell,** installed by `make install`, the dev container and CI's Check, Tests and Nightly jobs (`playwright install --only-shell chromium`).

## Options considered

| Option | For | Against |
|---|---|---|
| **Browser mode in Bun, two schemes as two instances (chosen)** | One runtime still. Every test is proved in both schemes without writing it twice | Each test run starts Chromium twice |
| Node.js in `.prototools` for browser mode | Vitest's documented runtime | Not needed: it works in Bun |
| jsdom or happy-dom | No browser to install | No real layout or computed styles, so neither scheme is tested |
| Screenshot tests now | Catch any visual change | Baselines per platform; two primitives don't need them |

## Consequences

- Easier: a token or a class that breaks a scheme, or a contrast, fails a test.
- Harder: CI installs Chromium in the jobs that run checks, about 100 MB.
- To revisit: screenshots, with baselines made in CI, when a component needs them.
