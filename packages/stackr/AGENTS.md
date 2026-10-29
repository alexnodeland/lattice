# AGENTS.md: stackr

The root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to stackr. stackr is not a Python library: it ships no wheel and inherits none of the Python projects' tasks. It holds the stack (`compose.yaml`, `deploy/`), the scripts that check and run it, and the copier application template (`template/`). Humans read [docs/stackr/](../../docs/stackr/index.md).

## Layout

| Path | What it is |
|---|---|
| `compose.yaml`, `Makefile`, `versions.env` | The local stack, its commands, and versions pinned outside compose |
| `deploy/` | Each service's configuration; `deploy/host/` (single host) and `deploy/aws/` (OpenTofu recipe) |
| `scripts/` | Python (`uv run`) and bash tools: validate, smoke, check-app, docs-reference, access-matrix |
| `template/` | The copier template's files; `copier.yml` holds its questions |
| `workers/diagrams/` | The diagrams worker, a Bun project (`diagrams-worker`) |
| `supabase/`, `trackers/` | Local Supabase's CLI config, and Plane and Vikunja compose files |

## Commands

Run `make` from `packages/stackr/` to list them. The ones that matter most:

```bash
make validate                         # every configuration, offline, no containers (as CI does)
make docs-reference                   # regenerate docs/stackr/reference/ from the files it describes
make up PROFILES=observability        # start the stack; make down / make reset to stop
make smoke                            # send telemetry through the running stack
```

Through moon:

```bash
moon run stackr:check                 # validate + reference + access-matrix
moon run stackr:validate              # make validate
moon run stackr:reference             # scripts/docs-reference --check
moon run stackr:access-matrix         # the template's access matrix against the libraries
moon run stackr:aws                   # deploy/aws tier 1 (needs Docker)
moon run stackr:template              # generate an application and run its checks
```

`images`, `aws-tier2`, `gotrue`, `files`, `umami-retention`, `smoke` and `smoke-app` need Docker or the network and are not part of `check`; run them when you change what their `inputs` in `moon.yml` list.

## Rules

- When you change a file the reference pages describe (compose, Grafana provisioning, `deploy/`), run `make docs-reference` and commit the regenerated `docs/stackr/reference/` pages; `stackr:reference` fails on drift.
- YAML here passes `yamllint --strict -c packages/stackr/.yamllint.yaml`, and shell scripts pass `shellcheck --external-sources` (with `.shellcheckrc`); both run in pre-commit. Many scripts have no extension: keep their shebang so `types: [shell]` finds them.
- `versions.env` is not read by Renovate. Bump a version there by hand, then run `make smoke`. GoTrue's image in `compose.yaml` and `deploy/aws/modules/stack/locals.tf` must match the pinned Supabase CLI (`moon run stackr:gotrue`); `EXCALIDRAW_VERSION` is held to the worker's `package.json` by `scripts/check-template`.
- Bind every published port to `STACKR_BIND` (127.0.0.1 by default). Never publish on all interfaces (ADR-0045).
- The root `copier.yml` includes `packages/stackr/copier.yml` and sets `_subdirectory`; keep both in step.

## The template

- Everything in `template/` is rendered into users' applications. `copier.yml` has no `_exclude`, so **do not add an `AGENTS.md`, notes or any other stray file under `template/`**: it would ship in every generated app. Rules for the template live here.
- Files ending in `.jinja` are rendered; names like `{% if use_portal %}brand{% endif %}` are conditional on answers. Everything else is copied verbatim.
- `copier update` from `stackr-v0.1.0` must apply with no conflict and give the same tree as a fresh generation (`tests/test_stackr_template_update.py`). A new question needs a default.
- `template/.dockerignore` must keep `.env` and `brand/**/.*` (`tests/test_stackr_dockerignore.py`).
- `scripts/check-template` checks the generated app's text files (`.md` included) and its portal modules; `tests/test_stackr_check_template.py` tests it.
- Change the template's grants and `stackr:access-matrix` must still pass against the libraries' catalogs and grantr's roles.
- After a template change, run `moon run stackr:template` (with `libraries`/`hosting` variants when you touched a conditional file).

## Safety

- `make reset` deletes the stack's data volumes, local Supabase's included. Don't run it unless asked.
- `.env` holds generated local secrets; it is ignored. Edit `.env.example` and `scripts/setup-env`, never commit `.env`.
