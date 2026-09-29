# Contributing to stackr

Thanks for helping. This guide covers how to set up, how work flows into `main`, and what "done" means here.

## Set up

You need Docker with Compose v2, [uv](https://docs.astral.sh/uv/) and `make`. The development tools are installed from `uv.lock`.

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
| `make up` | Start the stack; `make up PROFILES=observability` starts only the profiles you name |
| `make down` | Stop the stack, keeping its data |
| `make reset` | Stop the stack and delete its data volumes |
| `make ps` / `make logs` | Show the stack's containers, or follow their logs |
| `make dashboards` | Download the libraries' Grafana dashboards at the releases pinned in `versions.env` |
| `make validate` | Validate every configuration without starting containers, as CI does |
| `make smoke` | Send test telemetry through the running stack and check it arrives, as CI does |
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

Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`. Scopes are profile or area names: `compose`, `observability`, `langfuse`, `supabase`, `gateway`, `template`, `scripts`, `ci`, `docs`, `adr`, `rfc`. Mark breaking changes with `!` (`feat(gateway)!: ...`) and a `BREAKING CHANGE:` footer. The changelog is generated from these messages.

## Images and dependencies

- **Every image is pinned** to a version tag, never `latest` alone. Where a registry publishes only `latest`, the image is pinned by digest as well.
- **Dependabot** proposes updates weekly for the images in `compose.yaml`, the GitHub Actions and the development tools in `uv.lock`. An update is merged when CI passes.

## Secrets

`.env.example` holds settings and placeholders, never secrets. `scripts/setup-env` copies it to `.env`, which is gitignored, and generates a fresh value for every `generate:...` placeholder. Running it again keeps existing values and adds new keys. To add a secret, add it to `.env.example` as a `generate:...` value; the script's docstring lists the kinds. The defaults are for local development and single hosts.

## Design: RFCs, ADRs and evergreen docs

| Document | When | Where |
|---|---|---|
| **RFC** | Before a substantial change: a new service or profile, a new deployment target, changes to the application template's interface, cross-cutting behaviour | [`docs/rfcs/`][rfcs] |
| **ADR** | When a decision is made, including decisions made while implementing an RFC | [`docs/adr/`][adrs] |
| **Architecture docs** | Updated in the same PR as the change they describe | [`docs/architecture.md`][architecture] |

An RFC proposes; ADRs record what was decided; the architecture docs describe what exists now. A PR that changes what the architecture docs describe updates them in the same PR, never in a later cleanup. Accepted ADRs are not edited; a changed decision gets a new ADR that supersedes or amends the old one.

## Quality gates

CI runs the same scripts as `make validate` and `make smoke`.

`make validate` checks without starting the stack:

- **yamllint** in strict mode over every YAML file.
- **Compose configuration** for each profile on its own and all together, failing on warnings such as a variable missing from `.env`.
- **Each service's configuration with its own validator**, from the image `compose.yaml` pins: the Collector, Prometheus, Tempo and Loki.
- **Grafana dashboards:** valid JSON, unique uids, and only the provisioned data sources.
- **shellcheck** for the shell scripts, and **ruff** for the Python ones.

`make smoke` runs against a started stack (`make up`): it sends test telemetry through each profile and checks that it lands where it should. CI starts each profile and runs it.

## Definition of done

- [ ] `make validate` passes locally, and `make smoke` for the profiles the change touches.
- [ ] Images are pinned, and new settings are in `.env.example`.
- [ ] The architecture docs reflect the change.
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
[license]: LICENSE
[rfcs]: docs/rfcs/README.md
[security]: SECURITY.md
