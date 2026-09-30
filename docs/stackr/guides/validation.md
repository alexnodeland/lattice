# Validation and CI

stackr is configuration, and most of what can go wrong with configuration shows only when a service starts: a key it ignores, a guardrail it can't load, a variable missing from `.env`. So stackr checks its configuration two ways, with the same scripts locally and in CI: statically, without starting anything, and with containers, by starting the stack and following requests through it.

## `make validate`

`make validate` runs `scripts/validate`, which checks everything without starting the stack, and reports every failure before it exits. It needs `.env`, and creates it with `make env` if it's missing. It runs each service's own validator in a container without a network, so it needs Docker, and pulls the pinned images the first time.

| Step | What it checks |
|---|---|
| YAML lint | Every YAML file, with yamllint in strict mode |
| Compose configuration | `compose.yaml` for no profile, each profile on its own and all of them together, failing on any warning, such as a variable missing from `.env` |
| Grafana dashboards | Every dashboard is valid JSON with a title and a unique uid, and refers only to the provisioned data sources' uids |
| The Supabase project | Its project id differs from the Compose project's name, the Makefile and `compose.yaml` use it, and every Supabase container or network name in a tracked file, the template's and the documentation's included, is the one it gives |
| The gateway's configuration | Every model group a fallback names exists, guardrails use integrations that need no licence and valid modes, every `os.environ/` reference is set on the `litellm` service in `compose.yaml`, and no key is written into the file. LiteLLM has no validator of its own, and starts without a guardrail it can't load |
| The application template | Every variant rendered, under a 30-character slug whose package sorts before `conftest`, with nothing left unrendered, and its Python, YAML, shell scripts and Compose file through their linters (`scripts/check-template`) |
| Service configurations | Each with its own validator, run from the image `compose.yaml` pins, offline: `otelcol-contrib validate` for the Collector, `promtool check config` for Prometheus, `-config.verify` for Tempo and `-verify-config` for Loki |
| Shell scripts | shellcheck |
| Python scripts | ruff's formatter and linter |

The Supabase, gateway and dashboard checks are `scripts/check-config`, which covers what no service's own validator does.

## The documentation

stackr's pages are its section of lattice's site. `moon run lattice:docs` builds the whole site, as CI does:

1. `zensical build --strict --clean`: a broken link or anchor fails the build
2. `scripts/check_site.py site`: no list rendered as text, which happens when a list has no blank line before it, or a nested item isn't indented by its parent's text

`moon run stackr:reference` runs `scripts/docs-reference --check`: every generated block in `docs/stackr/reference/` matches the file it describes. `moon run lattice:docs-serve` serves the site with live reload at <http://localhost:8000>. When you change a file a reference page describes (`compose.yaml`, `.env.example`, the Collector's, Grafana's or the gateway's configuration, `copier.yml`, the template's files, the Makefile or `versions.env`), run `make docs-reference` to regenerate the page, and commit both.

## CI

lattice's `.github/workflows/ci.yml` runs on every pull request, and runs stackr's checks when the pull request changes what they read:

| Job | What it runs |
|---|---|
| Check | `stackr:check`: `stackr:validate`, which is `make validate`, after `make` generates a throwaway `.env`, which also tests `scripts/setup-env`; and `stackr:reference` |
| Template | Each of the six variants of the application template (three choices of libraries, with and without evals) on Python 3.12, and the largest on Python 3.14: generated from the pull request's commit, then its own `make check`, which is lint, strict types and the tests with 100% coverage |
| Smoke | The stack started three ways, with `make up` and `make smoke`, and `make smoke-app` beside the whole stack on local Supabase ([The smoke tests](smoke-tests.md)) |

The Template and Smoke jobs run `moon ci stackr:template` and `moon ci stackr:smoke`. Every job installs the tools from `uv.lock` with `uv sync --locked`, so CI runs the versions you run. lattice's nightly workflow runs every project's checks, stackr's included, on `main`.

## Building and publishing the site

lattice's `.github/workflows/docs.yml` builds the site on every push to `main` and when run by hand, and deploys it to GitHub Pages at <https://lattice.alexnodeland.com>, where stackr's section is <https://lattice.alexnodeland.com/stackr/>. Runs wait their turn, so an older commit never deploys after a newer one. The site always shows `main` ([ADR-0012](../adr/0012-documentation-site.md), [ADR-0014](../adr/0014-one-docs-build.md)).

## Dependencies

Every image is pinned to a version, and where a registry publishes only `latest`, by digest as well. Renovate proposes updates for the images in `compose.yaml`, lattice's GitHub Actions and the tools in `uv.lock`, and CI's smoke tests run on each update to stackr's images. `versions.env` is bumped by hand, and the template's library revisions by `make bump-libraries` ([Pinned versions](../reference/versions.md)).

## Git hooks

lattice's `make install`, at its root, installs the development tools and two git hooks through prek, which run the same tools as CI:

- **pre-commit:** whitespace and file checks, yamllint and shellcheck over stackr's files, ruff's formatter and linter, pyright, and actionlint and zizmor over the workflows
- **commit-msg:** the message must be a [Conventional Commit](https://www.conventionalcommits.org/), since pull requests are squash-merged and their titles become the changelog

[Contributing](../../project/contributing.md) has the rest of the workflow, and the definition of done.
