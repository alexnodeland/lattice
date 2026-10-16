# Pinned versions

stackr pins every version it depends on, in the file that uses it:

| What | Pinned in | Updated |
|---|---|---|
| Every service's image | `compose.yaml`, by tag, and by digest where a registry publishes only `latest` | By Renovate, with CI's smoke tests run on each update |
| The Supabase CLI, which pins Supabase's own images | `versions.env` | By hand. GoTrue's image in `compose.yaml` follows the version it runs ([Validation](../guides/validation.md)) |
| The development tools: linters, prek, Copier, Zensical | lattice's `uv.lock` | By Renovate |
| The GitHub Actions | lattice's `.github/workflows/` | By Renovate |

## `versions.env`

Renovate doesn't read this file. To bump a pin, change it here, then run `make docs-reference` and `make smoke`.

<!-- generated: versions-env -->

| Pin | Value |
|---|---|
| `SUPABASE_CLI_VERSION` | `2.118.0` |

<!-- end generated -->

- **`SUPABASE_CLI_VERSION`** is the CLI `make` runs through `npx` when no `supabase` is installed, and the one CI installs. The CLI's version decides Supabase's image versions.

## The template's libraries

The application template pins no library revision of its own. A generated application installs artifactr, reflexr and evalr from lattice, at the commit the template is rendered from, so they move with the template ([ADR-0018](../adr/0018-the-template-pins-the-libraries-at-its-own-commit.md), [The application template](../guides/template.md#the-libraries-revisions)).

## The file

??? example "The whole file: `versions.env`"

    ```bash
    --8<-- "packages/stackr/versions.env"
    ```
