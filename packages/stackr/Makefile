# stackr: everyday commands. `make` lists them.
#
# The tools (linters, pre-commit, git-cliff) run through uv, so their versions
# are the ones in uv.lock. The stack itself needs Docker with Compose v2.

.DEFAULT_GOAL := help
UV ?= uv
COMPOSE ?= docker compose

# The profiles `make up` starts: all of them unless you choose, for example
#   make up PROFILES=observability
ALL_PROFILES := observability postgres langfuse
PROFILES ?= $(ALL_PROFILES)
PROFILE_FLAGS = $(foreach profile,$(PROFILES),--profile $(profile))

# The Collector sends traces to Langfuse only when the langfuse profile runs.
comma := ,
TRACES_EXPORTERS = [otlp_grpc/tempo$(if $(filter langfuse,$(PROFILES)),$(comma) otlp_http/langfuse)]

.PHONY: help install env up down reset ps logs dashboards validate smoke changelog clean

help: ## List the available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the development tools and the git hooks
	$(UV) sync
	$(UV) run pre-commit install --hook-type pre-commit --hook-type commit-msg

env: ## Create or update .env, generating local secrets
	$(UV) run scripts/setup-env

.env: .env.example
	$(UV) run scripts/setup-env

up: .env dashboards ## Start the chosen PROFILES (default: all of them)
	STACKR_TRACES_EXPORTERS='$(TRACES_EXPORTERS)' $(COMPOSE) $(PROFILE_FLAGS) up --detach --wait

down: ## Stop the stack, keeping its data
	$(COMPOSE) --profile '*' down

reset: ## Stop the stack and delete its data volumes
	$(COMPOSE) --profile '*' down --volumes

ps: ## Show the stack's containers
	$(COMPOSE) --profile '*' ps

logs: ## Follow the logs of the running services
	$(COMPOSE) --profile '*' logs --follow --tail=100

dashboards: ## Download the libraries' Grafana dashboards pinned in versions.env
	$(UV) run scripts/fetch-dashboards

validate: .env ## Validate every configuration without starting containers, as CI does
	scripts/validate

smoke: ## Send test telemetry through the running stack and find it (PROFILES as for up)
	scripts/smoke $(PROFILES)

changelog: ## Regenerate CHANGELOG.md from conventional commits
	$(UV) run git-cliff --output CHANGELOG.md
	@$(UV) run python -c "import pathlib; p = pathlib.Path('CHANGELOG.md'); p.write_text(p.read_text().rstrip() + '\n')"

clean: ## Remove tool caches
	rm -rf .ruff_cache .cache
