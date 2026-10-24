# lattice: `make install` sets up the workspace, and `make check` runs what CI runs. Every other
# command is a moon task: `moon run <project>:<task>`, and `moon project <project>` lists a
# project's tasks.

.DEFAULT_GOAL := help
UV ?= uv
BUN ?= bun
MOON ?= moon

.PHONY: help install check dev dev-down dev-status dev-reset

help: ## List the available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install every package, group and extra, the web packages and their test browser, and the hooks
	$(UV) sync --all-packages --all-groups --all-extras
	$(BUN) install
	cd packages/portalr/web/ui && $(BUN) x --bun --no-install playwright install --only-shell chromium
	$(UV) run prek install
	git config blame.ignoreRevsFile .git-blame-ignore-revs

check: ## Run every project's checks, as CI does
	$(MOON) run :check

# Everything together (stackr ADR-0053): stackr's stack and an application beside it, generated
# into DEV_APP_DIR (.local/run/portal). scripts/dev says what each does, and its settings.
dev: ## Run stackr's stack and an application with the portal beside it; again is safe
	@scripts/dev up

dev-down: ## Stop both, keeping their data
	@scripts/dev down

dev-status: ## Show both projects' containers
	@scripts/dev status

dev-reset: ## Delete both projects' containers and volumes, once you confirm
	@scripts/dev reset
