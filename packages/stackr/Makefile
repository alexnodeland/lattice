# stackr: everyday commands. `make` lists them.
#
# The tools (linters and Copier) run through uv, so their versions are the ones in
# lattice's uv.lock. The stack itself needs Docker with Compose v2, the
# Supabase CLI for local Supabase, and jq for `validate` and `smoke`.

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
# `auth`, GoTrue alone, is the identity port on the postgres adapter, and is
# only started when chosen: local Supabase runs its own.
ALL_PROFILES := observability langfuse gateway
PROFILES ?= $(ALL_PROFILES)

# --- the database adapter (ADR-0009) -----------------------------------------
# STACKR_DATABASE in .env chooses it: supabase (default) or postgres. Profiles
# that keep data in PostgreSQL bring it up with them.
STACKR_DATABASE ?= $(or $(shell sed -n 's/^STACKR_DATABASE=//p' .env 2>/dev/null),supabase)
DATABASE_USERS := langfuse gateway auth
NEEDS_DATABASE = $(filter $(DATABASE_USERS),$(PROFILES))

# Local Supabase, run by its CLI: an installed `supabase`, or the pinned
# version through npx. SUPABASE_START_FLAGS can skip services, for example
#   make up SUPABASE_START_FLAGS="-x studio,imgproxy"
SUPABASE_PROJECT := stackr-supabase
SUPABASE_NETWORK := supabase_network_$(SUPABASE_PROJECT)
SUPABASE ?= $(shell command -v supabase 2>/dev/null || echo npx --yes supabase@$(SUPABASE_CLI_VERSION))
SUPABASE_START_FLAGS ?=
SUPABASE_RUNNING = $(shell docker ps -q --filter label=com.supabase.cli.project=$(SUPABASE_PROJECT))
# The CLI publishes Supabase's ports with no address of their own, so they bind where its network
# says: STACKR_BIND, as every other port does (127.0.0.1 unless you choose).
STACKR_BIND ?= $(or $(shell sed -n 's/^STACKR_BIND=//p' .env 2>/dev/null),127.0.0.1)
BINDING := com.docker.network.bridge.host_binding_ipv4
# Some Docker engines ignore that option (Docker Desktop 29 among them) and publish on every
# interface, where Supabase's well-known keys and its `postgres` password would be anyone's on the
# network. So before Supabase starts, scripts/binding-probe finds where Docker publishes on its
# network, and local Supabase starts only at STACKR_BIND alone, with no override (ADR-0045).

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

# STACKR_GATEWAY_MODELS in .env: the gateway's model groups, deploy/litellm/groups/<it>.yaml.
STACKR_GATEWAY_MODELS ?= $(or $(shell sed -n 's/^STACKR_GATEWAY_MODELS=//p' .env 2>/dev/null),providers)
ifeq ($(filter providers upstream,$(STACKR_GATEWAY_MODELS)),)
$(error STACKR_GATEWAY_MODELS must be providers or upstream, not '$(STACKR_GATEWAY_MODELS)')
endif
# The upstream's address and its models for the two groups, which it can't be without.
ifeq ($(STACKR_GATEWAY_MODELS),upstream)
UPSTREAM_NEEDS := STACKR_UPSTREAM_URL STACKR_UPSTREAM_DEFAULT_MODEL STACKR_UPSTREAM_FAST_MODEL
UPSTREAM_MISSING := $(strip $(foreach name,$(UPSTREAM_NEEDS),$(if $(or $($(name)),$(shell sed -n 's/^$(name)=//p' .env 2>/dev/null)),,$(name))))
ifneq ($(UPSTREAM_MISSING),)
$(error STACKR_GATEWAY_MODELS=upstream needs $(UPSTREAM_MISSING) in .env)
endif
endif

PROFILE_FLAGS = $(foreach profile,$(PROFILES) $(DATABASE_PROFILES),--profile $(profile))

# --- the recipe (RFC-0004) ---------------------------------------------------
# STACKR_RECIPE in .env: local (default), or host, a single host behind Caddy,
# whose overlay deploy/host/compose.prod.yaml publishes only Caddy's 80 and 443.
STACKR_RECIPE ?= $(or $(shell sed -n 's/^STACKR_RECIPE=//p' .env 2>/dev/null),local)
ifeq ($(STACKR_RECIPE),local)
COMPOSE_FILES :=
else ifeq ($(STACKR_RECIPE),host)
COMPOSE_FILES := -f compose.yaml -f deploy/host/compose.prod.yaml
# A host's identity is GoTrue: the auth profile starts with the rest.
ALL_PROFILES += auth
else
$(error STACKR_RECIPE must be local or host, not '$(STACKR_RECIPE)')
endif
STACK = $(COMPOSE) $(COMPOSE_FILES)

# The Collector sends traces to Langfuse only when the langfuse profile runs,
# and the gateway sends telemetry only when the Collector runs.
comma := ,
TRACES_EXPORTERS = [otlp_grpc/tempo$(if $(filter langfuse,$(PROFILES)),$(comma) otlp_http/langfuse)]
GATEWAY_TELEMETRY = $(if $(filter observability,$(PROFILES)),true,false)
COMPOSE_ENV = STACKR_TRACES_EXPORTERS='$(TRACES_EXPORTERS)' STACKR_GATEWAY_TELEMETRY=$(GATEWAY_TELEMETRY) $(DATABASE_ENV)

# scripts/smoke runs Compose as `make up` does, and the Supabase CLI as make runs it.
SMOKE = $(COMPOSE_ENV) STACKR_DATABASE=$(STACKR_DATABASE) STACKR_RECIPE=$(STACKR_RECIPE) \
	STACKR_COMPOSE_FILES="$(COMPOSE_FILES)" SUPABASE="$(SUPABASE)" scripts/smoke

# --- the task trackers (lattice RFC-0004) ------------------------------------
# Opt-in recipes, each a Compose project of its own beside the stack, joining its
# network: TRACKER=plane or vikunja. Their settings are stackr's .env.
TRACKERS := plane vikunja
TRACKER_STACK = $(COMPOSE) --env-file .env -f trackers/$(TRACKER)/compose.yaml
define need_tracker
$(if $(filter $(TRACKERS),$(TRACKER)),,$(error TRACKER must be one of $(TRACKERS), not '$(TRACKER)'))
endef

.PHONY: help env up down reset ps logs tenant portal-key tracker-up tracker-down tracker-check backup restore-drill validate smoke smoke-app docs-reference clean

help: ## List the available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Create or update .env, generating local secrets
	$(UV) run scripts/setup-env

.env: .env.example
	$(UV) run scripts/setup-env

up: .env ## Start the chosen PROFILES (default: all of them), with the database adapter they need
ifeq ($(STACKR_DATABASE)$(filter auth,$(PROFILES)),supabaseauth)
	$(error the auth profile is GoTrue for the postgres adapter: local Supabase runs its own Auth)
endif
ifeq ($(STACKR_RECIPE)$(STACKR_DATABASE),hostsupabase)
	$(error a single host runs on the postgres adapter, with the auth profile)
endif
ifeq ($(STACKR_RECIPE)$(filter auth,$(PROFILES)),host)
	$(error a single host needs the auth profile: make up PROFILES="observability langfuse gateway auth")
endif
	@bound=$$(docker network inspect -f '{{index .Options "$(BINDING)"}}' $(SUPABASE_NETWORK) 2>/dev/null) || \
	  { docker network create -o $(BINDING)=$(STACKR_BIND) $(SUPABASE_NETWORK) >/dev/null && bound=$(STACKR_BIND); }; \
	if [ "$$bound" != "$(STACKR_BIND)" ]; then \
	  echo "$(SUPABASE_NETWORK) publishes at '$$bound', not STACKR_BIND ($(STACKR_BIND)): make down, then docker network rm $(SUPABASE_NETWORK), then make up" >&2; \
	  exit 1; \
	fi
ifneq ($(strip $(START_SUPABASE)),)
	scripts/binding-probe $(SUPABASE_NETWORK) $(STACKR_BIND)
	$(SUPABASE) start $(SUPABASE_START_FLAGS)
endif
# Ten minutes: the first start pulls and builds every image. The app stack's up waits five.
	$(COMPOSE_ENV) $(STACK) $(PROFILE_FLAGS) up --detach --wait --wait-timeout 600 --build

down: ## Stop the stack, keeping its data
	$(STACK) --profile '*' down
	$(if $(SUPABASE_RUNNING),$(SUPABASE) stop)

reset: ## Stop the stack and delete its data volumes, local Supabase's included
	$(STACK) --profile '*' down --volumes
	$(if $(or $(SUPABASE_RUNNING),$(shell docker volume ls -q --filter label=com.supabase.cli.project=$(SUPABASE_PROJECT))),$(SUPABASE) stop --no-backup)
	@docker network rm $(SUPABASE_NETWORK) >/dev/null 2>&1 || true

ps: ## Show the stack's containers
	$(STACK) --profile '*' ps

logs: ## Follow the logs of the running services
	$(STACK) --profile '*' logs --follow --tail=100

tenant: ## Create a tenant's team and key on the gateway: make tenant NAME=acme [TENANT_FLAGS="--max-budget 20"]
	@if [ -z "$(NAME)" ]; then echo "usage: make tenant NAME=<tenant> [TENANT_FLAGS=...]"; exit 2; fi
	$(UV) run scripts/create-tenant $(NAME) $(TENANT_FLAGS)

portal-key: ## Create the read-only key portalr's admin reads spend with (PORTAL_LITELLM_KEY), not the master key; ARGS=--rotate replaces a lost one
	$(UV) run scripts/create-portal-key $(ARGS)

tracker-up: .env ## Start a task tracker beside the stack: make tracker-up TRACKER=plane (or vikunja)
	$(need_tracker)
	$(TRACKER_STACK) up --detach --wait --wait-timeout 600

tracker-down: ## Stop a task tracker, keeping its data: make tracker-down TRACKER=plane
	$(need_tracker)
	$(TRACKER_STACK) down

tracker-check: ## Check a tenant's tracker is provisioned, changing nothing: make tracker-check TENANT=acme TRACKER=plane APP_ENV=<the app's .env>
	@if [ -z "$(TENANT)" ]; then echo "usage: make tracker-check TENANT=<tenant> TRACKER=plane|vikunja [APP_ENV=<the application's .env>]"; exit 2; fi
	$(need_tracker)
	$(UV) run scripts/tracker-check $(TENANT) --tracker $(TRACKER) $(if $(APP_ENV),--app-env $(APP_ENV))

backup: ## On a single host: back up PostgreSQL and ClickHouse to the BACKUP_S3_* bucket now
	$(if $(COMPOSE_FILES),deploy/host/backup,$(error backups are the single host's: set STACKR_RECIPE=host))

restore-drill: ## On a single host: restore the latest backups beside the stack, check them, and report
	$(if $(COMPOSE_FILES),deploy/host/restore-drill,$(error the restore drill is the single host's: set STACKR_RECIPE=host))

validate: .env ## Validate every configuration without starting containers, as CI does
	scripts/validate

smoke: ## Send test telemetry through the running stack and find it (PROFILES as for up)
	$(SMOKE) $(PROFILES) $(if $(NEEDS_DATABASE),database) $(if $(COMPOSE_FILES),edge)

smoke-app: ## Run an application from the template beside the running stack, trace its agents, and bridge an incident
	$(SMOKE) app

docs-reference: ## Regenerate the reference pages from the files they describe
	$(UV) run scripts/docs-reference

clean: ## Remove tool caches
	rm -rf .ruff_cache .cache
