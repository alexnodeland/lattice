# Pinned versions

stackr pins every version it depends on, in the file that uses it:

| What | Pinned in | Updated |
|---|---|---|
| Every service's image | `compose.yaml`, by tag, and by digest where a registry publishes only `latest` | Weekly by Dependabot, merged when CI's smoke tests pass |
| The Supabase CLI, which pins Supabase's own images, and the libraries' Grafana dashboards | `versions.env` | By hand |
| The libraries the application template pins by default | `copier.yml` | By hand |
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

The libraries aren't on PyPI yet, so the application template pins each to a commit of its repository: each library's `main` when the template was last updated. An application keeps the revisions it was generated with, and moves them itself ([The application template](../guides/template.md#the-libraries-revisions)).

<!-- generated: template-revisions -->

| Library | Commit the template pins by default |
|---|---|
| artifactr | `e890aca037c0160f49812778a7d6fbbd0c257889` |
| reflexr | `5c1fb77c7b7793a9741e97c0ee825b638ea8ca39` |
| evalr | `62582e2a677947bbb540e367e28bb6ad7d33b7f9` |

<!-- end generated -->

## The file

??? example "The whole file: `versions.env`"

    ```bash
    --8<-- "versions.env"
    ```
