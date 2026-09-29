# Makefile targets

Every command is a `make` target; `make` on its own lists them. The tools run through `uv`, at the versions in `uv.lock`.

## Commands

<!-- generated: makefile-targets -->

| Command | What it does |
|---|---|
| `make help` | List the available commands |
| `make install` | Install the development tools and the git hooks |
| `make env` | Create or update .env, generating local secrets |
| `make up` | Start the chosen PROFILES (default: all of them), with the database adapter they need |
| `make down` | Stop the stack, keeping its data |
| `make reset` | Stop the stack and delete its data volumes, local Supabase's included |
| `make ps` | Show the stack's containers |
| `make logs` | Follow the logs of the running services |
| `make dashboards` | Download the libraries' Grafana dashboards pinned in versions.env |
| `make tenant` | Create a tenant's team and key on the gateway: make tenant NAME=acme [TENANT_FLAGS="--max-budget 20"] |
| `make bump-libraries` | Pin the template's libraries to their main commits: make bump-libraries [BUMP_FLAGS="--check" or "artifactr=REV"] |
| `make validate` | Validate every configuration without starting containers, as CI does |
| `make smoke` | Send test telemetry through the running stack and find it (PROFILES as for up) |
| `make smoke-app` | Run an application from the template beside the running stack, and trace its agents |
| `make docs` | Build the documentation site strictly, and check its reference pages and lists, as CI does |
| `make docs-serve` | Serve the documentation site with live reload at http://localhost:8000 |
| `make docs-reference` | Regenerate the reference pages from the files they describe |
| `make changelog` | Regenerate CHANGELOG.md from conventional commits |
| `make clean` | Remove tool caches and the built site |

<!-- end generated -->

## Variables

Set a variable on the command line (`make up PROFILES=observability`) or in the environment. `STACKR_DATABASE` is read from `.env` unless you set it.

<!-- generated: makefile-variables -->

| Variable | Default |
|---|---|
| `UV` | `uv` |
| `COMPOSE` | `docker compose` |
| `PROFILES` | `$(ALL_PROFILES)` |
| `STACKR_DATABASE` | `$(or $(shell sed -n 's/^STACKR_DATABASE=//p' .env 2>/dev/null),supabase)` |
| `SUPABASE` | `$(shell command -v supabase 2>/dev/null || echo npx --yes supabase@$(SUPABASE_CLI_VERSION))` |
| `SUPABASE_START_FLAGS` | empty |

<!-- end generated -->

`make tenant` also reads `NAME`, the tenant, and `TENANT_FLAGS`, the options `scripts/create-tenant` takes ([The LLM gateway](../guides/gateway.md#tenants)). `make bump-libraries` reads `BUMP_FLAGS`, the option and `LIBRARY=REV` pins `scripts/bump-libraries` takes ([The application template](../guides/template.md#in-stackr-bumping-the-templates-pins)). `make smoke-app` reads `SMOKE_APP_PORT`, and both smoke targets `SMOKE_TIMEOUT` ([The smoke tests](../guides/smoke-tests.md)).

## The file

??? example "The whole file: `Makefile`"

    ```makefile
    --8<-- "Makefile"
    ```
