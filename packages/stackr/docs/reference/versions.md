# Pinned versions

stackr pins every version it depends on, in the file that uses it:

| What | Pinned in | Updated |
|---|---|---|
| Every service's image | `compose.yaml`, by tag, and by digest where a registry publishes only `latest` | Weekly by Dependabot, merged when CI's smoke tests pass |
| The Supabase CLI, which pins Supabase's own images, and the libraries' Grafana dashboards | `versions.env` | By hand |
| The libraries the application template pins by default | `copier.yml` | By `make bump-libraries`, run by hand |
| The development tools: linters, pre-commit, git-cliff, Copier, Zensical | `uv.lock` | Weekly by Dependabot |
| The GitHub Actions | `.github/workflows/` | Weekly by Dependabot |

## `versions.env`

Dependabot doesn't read this file. To bump a pin, change it here, then run `make docs-reference` and `make smoke`.

<!-- generated: versions-env -->

| Pin | Value |
|---|---|
| `SUPABASE_CLI_VERSION` | `2.118.0` |
| `ARTIFACTR_DASHBOARDS_VERSION` | not pinned |
| `ARTIFACTR_DASHBOARDS_SHA256` | not pinned |
| `REFLEXR_DASHBOARDS_VERSION` | not pinned |
| `REFLEXR_DASHBOARDS_SHA256` | not pinned |

<!-- end generated -->

- **`SUPABASE_CLI_VERSION`** is the CLI `make` runs through `npx` when no `supabase` is installed, and the one CI installs. The CLI's version decides Supabase's image versions.
- **`<LIBRARY>_DASHBOARDS_VERSION`** is the library release whose dashboards `make dashboards` downloads; an empty version is skipped. **`<LIBRARY>_DASHBOARDS_SHA256`**, when set, must match the downloaded archive ([Observability](../guides/observability.md#the-libraries-dashboards-by-version)).

## The template's library revisions

The libraries aren't on PyPI yet, so the application template pins each to a commit of its repository: each library's `main` when the template was last updated. `make bump-libraries` moves them to each library's current `main` (evalr's to the commit reflexr pins) and regenerates this table, and `make bump-libraries BUMP_FLAGS=--check` fails when one is behind ([bumping the template's defaults](../guides/template.md#in-stackr-bumping-the-templates-defaults)). An application keeps the revisions it was generated with, and moves them itself ([The application template](../guides/template.md#the-libraries-revisions)).

<!-- generated: template-revisions -->

| Library | Commit the template pins by default |
|---|---|
| artifactr | `9c92a7f7685df14861dd1077539b595cb6c1ede4` |
| reflexr | `f91a89409e6d42c8d7ac0bca945856e39229476f` |
| evalr | `62582e2a677947bbb540e367e28bb6ad7d33b7f9` |

<!-- end generated -->

## The file

??? example "The whole file: `versions.env`"

    ```bash
    --8<-- "versions.env"
    ```
