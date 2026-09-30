# Contributing to stackr

Thanks for helping. This guide covers how to set up, how work flows into `main`, and what "done" means here.

## Set up

You need Docker with Compose v2, [uv](https://docs.astral.sh/uv/), `make` and `jq`. The development tools are installed from `uv.lock`. Local Supabase needs the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) (`brew install supabase/tap/supabase`); without it, `make` runs the version pinned in `versions.env` through `npx`, which needs Node.

```bash
git clone git@github.com:alexnodeland/stackr.git
cd stackr
make install        # the development tools and the git hooks
make env            # .env, with local secrets generated
make validate       # every configuration, checked without starting containers: the same gates as CI
```

Run `make` on its own to list every command:

| Command | What it does |
|---|---|
| `make env` | Create or update `.env` from `.env.example`, generating local secrets |
| `make up` | Start the stack, with local Supabase; `make up PROFILES=observability` starts only the profiles you name |
| `make down` | Stop the stack and local Supabase, keeping their data |
| `make reset` | Stop the stack and local Supabase, and delete their data volumes |
| `make ps` / `make logs` | Show the stack's containers, or follow their logs |
| `make dashboards` | Download the libraries' Grafana dashboards at the releases pinned in `versions.env` |
| `make tenant NAME=acme` | Create a tenant's team and key on the gateway |
| `make bump-libraries` | Pin the application template's libraries to each one's current `main`; `BUMP_FLAGS=--check` only reports whether they are behind |
| `make validate` | Validate every configuration without starting containers, as CI does |
| `make smoke` | Send test telemetry through the running stack and check it arrives, as CI does |
| `make smoke-app` | Run an application from the template beside the running stack, and trace its agents through the gateway, as CI does |
| `make docs` | Build the [documentation site][site] strictly, changelog included, as CI does |
| `make docs-serve` | Serve the documentation site with live reload at <http://localhost:8000> |
| `make docs-reference` | Regenerate the site's reference pages from the files they describe |
| `make changelog` | Regenerate `CHANGELOG.md` from commit history |

## How work flows: trunk-based development

`main` is the trunk and is always usable, as in the rest of the family ([artifactr ADR-0014][family-process]).

1. Branch from the latest `main`. Keep branches short-lived: hours to a day or two, not weeks.
2. Keep pull requests small and focused on one change. Split large work into a sequence of PRs that each leave `main` green.
3. CI must pass before merging.
4. Pull requests are squash-merged, so the PR title becomes the commit on `main`. Write it as a [Conventional Commit](https://www.conventionalcommits.org/).
5. Delete the branch after merging. Don't stack branches on unmerged branches.

### Commit messages

Commits and PR titles follow Conventional Commits, checked by a `commit-msg` hook:

```
feat(observability): add Tempo's metrics generator
fix(gateway): reach local model servers through host.docker.internal
docs(adr): record how metrics reach Prometheus
```

Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`. Scopes are profile or area names: `compose`, `observability`, `langfuse`, `supabase`, `gateway`, `template`, `scripts`, `ci`, `docs`, `adr`, `rfc`. Mark breaking changes with `!` (`feat(gateway)!: ...`) and a `BREAKING CHANGE:` footer. The changelog is generated from these messages. Don't edit `CHANGELOG.md` by hand: the documentation site regenerates it from `main`'s history on every build, and `make changelog` regenerates the file before a release.

## Images and dependencies

- **Every image is pinned** to a version tag, never `latest` alone. Where a registry publishes only `latest`, the image is pinned by digest as well. The Supabase CLI, which pins Supabase's images, is pinned in `versions.env`.
- **Dependabot** proposes updates weekly for the images in `compose.yaml`, the GitHub Actions and the development tools in `uv.lock`. An update is merged when CI passes.
- **The libraries the application template pins,** artifactr and reflexr, install from GitHub by commit, not from PyPI, and Dependabot doesn't see them. `make bump-libraries` moves each pin in `copier.yml` to its library's current `main`, regenerates the reference pages, and prints each change with a link comparing the commits: put that in the pull request's description. `BUMP_FLAGS=--check` changes nothing and fails when a pin is behind; `BUMP_FLAGS="artifactr=<commit SHA>"` pins one library to a commit, a branch or a tag. The template doesn't pin evalr: it comes with the libraries, at the commit their own sources pin ([ADR-0013](docs/adr/0013-how-the-template-pins-the-libraries.md)). The pull request's Template and Smoke jobs generate applications on the new pins.

## Secrets

`.env.example` holds settings and placeholders, never secrets. `scripts/setup-env` copies it to `.env`, which is gitignored, and generates a fresh value for every `generate:...` placeholder. Running it again keeps existing values and adds new keys. To add a secret, add it to `.env.example` as a `generate:...` value; the script's docstring lists the kinds. The defaults are for local development and single hosts.

## Design: RFCs, ADRs and evergreen docs

| Document | When | Where |
|---|---|---|
| **RFC** | Before a substantial change: a new service or profile, a new deployment target, changes to the application template's interface, cross-cutting behaviour | [`docs/rfcs/`][rfcs] |
| **ADR** | When a decision is made, including decisions made while implementing an RFC | [`docs/adr/`][adrs] |
| **Architecture docs** | Updated in the same PR as the change they describe | [`docs/architecture.md`][architecture] |
| **Guides and reference** | Updated in the same PR as the change they describe | [`docs/guides/`][guides] and [`docs/reference/`][reference], published at [stackr.alexnodeland.com][site] |

An RFC proposes; ADRs record what was decided; the architecture docs, guides and reference describe what exists now. A PR that changes what they describe updates them in the same PR, never in a later cleanup. The reference pages' tables are generated from the files they describe: after changing one of those files, run `make docs-reference` and commit the result. Accepted ADRs are not edited; a changed decision gets a new ADR that supersedes or amends the old one.

## Quality gates

CI runs the same scripts as `make validate` and `make smoke`.

`make validate` checks without starting the stack:

- **yamllint** in strict mode over every YAML file.
- **Compose configuration** for each profile on its own and all together, failing on warnings such as a variable missing from `.env`.
- **Each service's configuration with its own validator**, from the image `compose.yaml` pins: the Collector, Prometheus, Tempo and Loki.
- **The Supabase project's names:** every tracked file, the template's included, names Supabase's containers and network by the project id in `supabase/config.toml`.
- **The gateway's configuration:** fallbacks, guardrails and environment references, since LiteLLM has no validator and starts without a guardrail it can't load.
- **Grafana dashboards:** valid JSON, unique uids, and only the provisioned data sources.
- **The application template,** rendered in every variant: nothing left unrendered, and the generated Python, YAML, shell scripts and Compose file pass their linters.
- **shellcheck** for the shell scripts, and **ruff** for the Python ones.

CI also generates each variant of the template and runs its own `make check`. To do the same locally, render one and check it:

```bash
uv run copier copy --defaults --vcs-ref HEAD --data libraries=both . /tmp/my-app
cd /tmp/my-app && git init && make install && make check
```

`make docs` builds the documentation site as the Docs workflow does on every pull request ([ADR-0014](docs/adr/0014-one-docs-build.md)): the changelog regenerated from the history, the reference pages checked against their files, a strict build that fails on a broken link or anchor, and a check that every list rendered as a list. It leaves `CHANGELOG.md` regenerated in your working tree; don't commit that. In Markdown, put a blank line before every list, and indent a nested item by its parent's text: two spaces after `-`, three after `1.`.

`make smoke` runs against a started stack (`make up`): it sends test telemetry through each profile and checks that it lands where it should. CI starts each profile and runs it. `make smoke-app`, against the whole stack on local Supabase, runs an application generated from the template in its app profile and traces its agents through the gateway.

## Definition of done

- [ ] `make validate` passes locally, and `make smoke` for the profiles the change touches; `make smoke-app` too when the template changes.
- [ ] Images are pinned, and new settings are in `.env.example`.
- [ ] The architecture docs, guides and reference reflect the change, and `make docs` passes.
- [ ] New decisions have an ADR; substantial proposals had an RFC.
- [ ] The PR title is a Conventional Commit.

## Reporting bugs and proposing features

Use the issue templates. For security issues, follow [SECURITY.md][security] instead of opening a public issue.

## Code of conduct

This project follows the [Code of Conduct][code-of-conduct]. By participating, you agree to uphold it.

## License

By contributing, you agree that your contributions are licensed under the [MIT License][license].

<!-- Link targets live here so the documentation site can redefine them for its own layout. -->

[adrs]: docs/adr/README.md
[architecture]: docs/architecture.md
[code-of-conduct]: CODE_OF_CONDUCT.md
[family-process]: https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0014-trunk-based-development-with-rfcs-and-adrs.md
[guides]: docs/guides/stack.md
[license]: LICENSE
[reference]: docs/reference/index.md
[rfcs]: docs/rfcs/README.md
[security]: SECURITY.md
[site]: https://stackr.alexnodeland.com
