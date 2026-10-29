# AGENTS.md: portalr

The root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to portalr's Python package. The web packages under `web/` have their own ([web/AGENTS.md](web/AGENTS.md)).

## What this is

The router an application mounts to serve the two UIs, `app` and `admin`, beside the libraries' routers, plus the reads they need (tenant-filtered), invites, people, brand kits and analytics. Read [docs/portalr/architecture.md](../../docs/portalr/architecture.md) before changing a module, and update it in the same PR.

- `src/portalr/`: the package. `static/` is the UIs' build output (git-ignored): never edit it.
- `schemas/`: `portalr.openapi.json` and `integrations.json`, generated.
- `scripts/`: the checks over the built UIs (`check_size.py`, `check_wasm.py`, `check_wheel.py`, `check_liberation.py`), `api` and smoke scripts.
- `tests/`: unit tests; `tests/app/` is the test application the `bdd` and `api` tasks run; `tests/acceptance/` the two-tenant test.
- `bruno/`: the Bruno collection `portalr:api` runs, with the tools up and down.

## Commands

```bash
moon run portalr:check            # lint, typecheck, test, plus ui-in-wheel, size, wasm (builds the UIs)
moon run portalr:test
moon run portalr:schema           # after changing a route or lattice's integrations
moon run portalr:brand            # after editing the default brand kit (src/portalr/brand/)
moon run portalr:api              # acceptance: test app, tools, Bruno, Schemathesis; needs Docker
```

`portalr:build` depends on `app:build` and `admin:build`, so `check` builds the UIs too. `portalr:liberation` needs the network and is not run in CI.

## Rules

- **Every read is filtered by tenant,** in one module, over the shared stores ([ADR-0006](../../docs/portalr/adr/0006-shared-stores-every-read-filtered.md)). Don't query a store around it.
- **The browser calls each package's own routes.** Don't proxy another library's API or re-declare its types here ([ADR-0001](../../docs/portalr/adr/0001-a-router-the-application-mounts.md)).
- **Commit what the generators write.** Tests fail while `schemas/` drifts from the router (`portalr:schema`), or `web/ui/src/tokens.css` from the default brand kit (`portalr:brand`).
- **The budgets are tested.** `size-budget.json` (gzip ceiling per UI, [ADR-0040](../../docs/portalr/adr/0040-scenarios-against-a-generated-application-and-size-budgets.md)) and `web/wasm-allowlist.json` ([ADR-0041](../../docs/portalr/adr/0041-first-party-webassembly-in-the-apps-policy.md)) are inputs of `test`; raise a ceiling or allow a module only with a reason in the PR.
- **The wheel's `license` expression** in `pyproject.toml` must cover the bundled JavaScript's licences (`portalr:licence-expression`); exceptions live in `web/notices/policy.json` and must each still be needed (`portalr:licence-exceptions`).
- **Layering:** `tests/test_layering.py` lists what each module may import. portalr depends on grantr, artifactr, reflexr, relayr and lattice-core only as `pyproject.toml` declares.
- Root tests hold portalr to its docs and web sources: `tests/test_portalr_guides.py` (the guides' examples run and their facts match the code), `tests/test_portalr_settings_labels.py` (admin labels every setting lattice-core declares), `tests/test_portalr_web_tokens.py` (no colour literals in the web sources).
