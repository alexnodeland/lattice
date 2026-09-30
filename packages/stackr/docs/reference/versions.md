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

<!-- end generated -->

- **`SUPABASE_CLI_VERSION`** is the CLI `make` runs through `npx` when no `supabase` is installed, and the one CI installs. The CLI's version decides Supabase's image versions.
- **`<LIBRARY>_DASHBOARDS_VERSION`** is the library release whose dashboards `make dashboards` downloads; an empty version is skipped. **`<LIBRARY>_DASHBOARDS_SHA256`**, when set, must match the downloaded archive ([Observability](../guides/observability.md#the-libraries-dashboards-by-version)).

## The template's library revisions

The libraries aren't on PyPI yet, so the application template pins artifactr and reflexr each to a commit of its repository: each library's `main` when the template was last updated. evalr comes with them, at the commit their own sources pin. `make bump-libraries` moves the pins to each library's current `main` and regenerates this table, and `make bump-libraries BUMP_FLAGS=--check` fails when one is behind ([bumping the template's pins](../guides/template.md#in-stackr-bumping-the-templates-pins)). An application moves to them with `copier update` ([The application template](../guides/template.md#the-libraries-revisions)).

<!-- generated: template-revisions -->

| Library | Commit the template pins |
|---|---|
| artifactr | `1a635ecb9800c2e414221e7293e8a2de2fdb600c` |
| reflexr | `dc2d05916cd6d1bf36b7c2b26e29663dfdddc338` |

<!-- end generated -->

## The file

??? example "The whole file: `versions.env`"

    ```bash
    --8<-- "versions.env"
    ```
