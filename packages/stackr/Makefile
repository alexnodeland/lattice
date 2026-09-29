# stackr: everyday commands. `make` lists them.
#
# The tools (linters, pre-commit, git-cliff) run through uv, so their versions
# are the ones in uv.lock. The stack itself needs Docker with Compose v2, and
# the Supabase CLI for local Supabase.

.DEFAULT_GOAL := help
UV ?= uv
COMPOSE ?= docker compose

include versions.env

# The stack's images are multi-architecture and run natively. A
# DOCKER_DEFAULT_PLATFORM that forces another architecture would run them
# under emulation, where Supabase's Realtime fails to start.
unexport DOCKER_DEFAULT_PLATFORM

# The profiles `make up` starts: all of them unless you choose, for example
#   make up PROFILES=observability
ALL_PROFILES := observability langfuse gateway
PROFILES ?= $(ALL_PROFILES)

# --- the database adapter (ADR-0009) -----------------------------------------
# STACKR_DATABASE in .env chooses it: supabase (default) or postgres. Profiles
# that keep data in PostgreSQL bring it up with them.
STACKR_DATABASE ?= $(or $(shell sed -n 's/^STACKR_DATABASE=//p' .env 2>/dev/null),supabase)
DATABASE_USERS := langfuse gateway
NEEDS_DATABASE = $(filter $(DATABASE_USERS),$(PROFILES))

# Local Supabase, run by its CLI: an installed `supabase`, or the pinned
# version through npx. SUPABASE_START_FLAGS can skip services, for example
#   make up SUPABASE_START_FLAGS="-x studio,imgproxy"
SUPABASE_PROJECT := stackr-supabase
SUPABASE_NETWORK := supabase_network_$(SUPABASE_PROJECT)
SUPABASE ?= $(shell command -v supabase 2>/dev/null || echo npx --yes supabase@$(SUPABASE_CLI_VERSION))
SUPABASE_START_FLAGS ?=
SUPABASE_RUNNING = $(shell docker ps -q --filter label=com.supabase.cli.project=$(SUPABASE_PROJECT))

ifeq ($(STACKR_DATABASE),supabase)
DATABASE_PROFILES :=
# Compose's defaults are local Supabase's host and fixed admin password.
DATABASE_ENV :=
START_SUPABASE = $(NEEDS_DATABASE)
else ifeq ($(STACKR_DATABASE),postgres)
DATABASE_PROFILES = $(if $(NEEDS_DATABASE),postgres)
# The admin password is read from .env by the shell, so it never appears on a
# command line.
DATABASE_ENV = STACKR_DB_HOST=postgres STACKR_DB_ADMIN_PASSWORD="$$(sed -n 's/^POSTGRES_ADMIN_PASSWORD=//p' .env)"
START_SUPABASE :=
else
$(error STACKR_DATABASE must be supabase or postgres, not '$(STACKR_DATABASE)')
endif

PROFILE_FLAGS = $(foreach profile,$(PROFILES) $(DATABASE_PROFILES),--profile $(profile))

# The Collector sends traces to Langfuse only when the langfuse profile runs,
# and the gateway sends telemetry only when the Collector runs.
comma := ,
TRACES_EXPORTERS = [otlp_grpc/tempo$(if $(filter langfuse,$(PROFILES)),$(comma) otlp_http/langfuse)]
GATEWAY_TELEMETRY = $(if $(filter observability,$(PROFILES)),true,false)
COMPOSE_ENV = STACKR_TRACES_EXPORTERS='$(TRACES_EXPORTERS)' STACKR_GATEWAY_TELEMETRY=$(GATEWAY_TELEMETRY) $(DATABASE_ENV)

.PHONY: help install env up down reset ps logs dashboards tenant validate smoke changelog clean

help: ## List the available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the development tools and the git hooks
	$(UV) sync
	$(UV) run pre-commit install --hook-type pre-commit --hook-type commit-msg

env: ## Create or update .env, generating local secrets
	$(UV) run scripts/setup-env

.env: .env.example
	$(UV) run scripts/setup-env

up: .env dashboards ## Start the chosen PROFILES (default: all of them), with the database adapter they need
	@docker network inspect $(SUPABASE_NETWORK) >/dev/null 2>&1 || docker network create $(SUPABASE_NETWORK) >/dev/null
ifneq ($(strip $(START_SUPABASE)),)
	$(SUPABASE) start $(SUPABASE_START_FLAGS)
endif
	$(COMPOSE_ENV) $(COMPOSE) $(PROFILE_FLAGS) up --detach --wait

down: ## Stop the stack, keeping its data
	$(COMPOSE) --profile '*' down
	$(if $(SUPABASE_RUNNING),$(SUPABASE) stop)

reset: ## Stop the stack and delete its data volumes, local Supabase's included
	$(COMPOSE) --profile '*' down --volumes
	$(if $(or $(SUPABASE_RUNNING),$(shell docker volume ls -q --filter label=com.supabase.cli.project=$(SUPABASE_PROJECT))),$(SUPABASE) stop --no-backup)
	@docker network rm $(SUPABASE_NETWORK) >/dev/null 2>&1 || true

ps: ## Show the stack's containers
	$(COMPOSE) --profile '*' ps

logs: ## Follow the logs of the running services
	$(COMPOSE) --profile '*' logs --follow --tail=100

dashboards: ## Download the libraries' Grafana dashboards pinned in versions.env
	$(UV) run scripts/fetch-dashboards

tenant: ## Create a tenant's team and key on the gateway: make tenant NAME=acme [TENANT_FLAGS="--max-budget 20"]
	@if [ -z "$(NAME)" ]; then echo "usage: make tenant NAME=<tenant> [TENANT_FLAGS=...]"; exit 2; fi
	$(UV) run scripts/create-tenant $(NAME) $(TENANT_FLAGS)

validate: .env ## Validate every configuration without starting containers, as CI does
	scripts/validate

smoke: ## Send test telemetry through the running stack and find it (PROFILES as for up)
	$(COMPOSE_ENV) STACKR_DATABASE=$(STACKR_DATABASE) scripts/smoke $(PROFILES) $(if $(NEEDS_DATABASE),database)

changelog: ## Regenerate CHANGELOG.md from conventional commits
	$(UV) run git-cliff --output CHANGELOG.md
	@$(UV) run python -c "import pathlib; p = pathlib.Path('CHANGELOG.md'); p.write_text(p.read_text().rstrip() + '\n')"

clean: ## Remove tool caches
	rm -rf .ruff_cache .cache
