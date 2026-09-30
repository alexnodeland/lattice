# lattice: `make install` sets up the workspace, and `make check` runs what CI runs. Every other
# command is a moon task: `moon run <project>:<task>`, and `moon project <project>` lists a
# project's tasks.

.DEFAULT_GOAL := help
UV ?= uv
MOON ?= moon

.PHONY: help install check

help: ## List the available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install every package, dependency group and extra, and the git hooks
	$(UV) sync --all-packages --all-groups --all-extras
	$(UV) run prek install
	git config blame.ignoreRevsFile .git-blame-ignore-revs

check: ## Run every project's checks, as CI does
	$(MOON) run :check
