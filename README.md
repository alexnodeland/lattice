# lattice

The family's packages, in one repository: libraries for applications in which people and agents work together, and the stack they run on.

| Package | What it is | Distribution |
|---|---|---|
| [artifactr](packages/artifactr) | Chat applications where people and agents collaborate through shared, versioned artifacts | `artifactr-ai` |
| [reflexr](packages/reflexr) | Rules over event streams that run LLM workflows: pydantic-ai agents, pydantic-graph graphs and functions | `reflexr` |
| [evalr](packages/evalr) | Typed evaluation of agent systems: judges that give typed verdicts, trained on people's feedback and measured against it | `evalr` |
| [relayr](packages/relayr) | The bridge between artifactr and reflexr: events from chats and artifacts become events for rules, and runs act back in the chat | `relayr-ai` |
| [stackr](packages/stackr) | The infrastructure the libraries run on (local Supabase, the LiteLLM gateway, OpenTelemetry, Grafana and Langfuse), and an application template | none |

Two more are planned. **grantr** is identity and access for artifactr and reflexr: users, groups, roles and permissions, bound to tenants and workspaces and checked by their authorize hooks. **portalr** is the portal into the system: chat with your agents, see artifacts, rules and runs, and manage access, traces, feedback, evals and analytics.

The reference implementations are in [`examples/`](examples): docplan is artifactr's, and oncall is reflexr's.

The documentation is at <https://lattice.alexnodeland.com>, with a section per package.

## Installing a package

Each package stays what it was: its own name, version, dependencies, extras, changelog and releases. Until the packages are on PyPI, install one from its subdirectory at a release tag, which carries the package's name:

```bash
uv add "artifactr-ai @ git+https://github.com/alexnodeland/lattice@artifactr-v0.1.0#subdirectory=packages/artifactr"
```

## Developing

You need [uv](https://docs.astral.sh/uv/), and [moon](https://moonrepo.dev/moon) at the version in `.prototools` (`proto use` installs both). Docker runs stackr's stack and the PostgreSQL tests.

```bash
make install    # every package, dependency group and extra, in one environment
make check      # every project's checks, as CI runs them: moon run :check
```

[CONTRIBUTING.md](CONTRIBUTING.md) has the rest. Every package is released under the [MIT License](LICENSE).
