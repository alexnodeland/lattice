# AGENTS.md: @portalr/ui

[web/AGENTS.md](../AGENTS.md) applies; this adds what is specific to `ui`.

- Import only client's types from `@portalr/client` ([ADR-0015](../../../../docs/portalr/adr/0015-the-chat-components-and-streamdown.md)); export what app and admin use from `src/index.ts` or the subpaths in `package.json`'s `exports`.
- Tests run in Chromium through Vitest's browser mode, twice: light and dark, with reduced motion (`vitest.config.ts`). Install the browser with `moon run ui:chromium`. Check a colour in both schemes.
- `*.screenshot.test.tsx` run only where `CI` is set, against Linux baselines in `src/__screenshots__/`. Don't generate baselines locally. To add or update one, take the `ui-screenshots` artifact from the failed Check job, review it, and commit its `-reference` (new) or `-actual` (changed) file without that suffix ([CONTRIBUTING.md](../../../../CONTRIBUTING.md)).
- `src/tokens.css` is written by `moon run portalr:brand`; edit the brand kit, not the file.
- `csp/policy.txt` is held to the router's CSP by a portalr test; change them together.
- Fonts under `fonts/` are checked against upstream by `portalr:liberation`; don't replace them by hand.
