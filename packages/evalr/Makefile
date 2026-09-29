# evalr: everyday developer commands. `make` lists them.
#
# Everything runs through uv, so the versions used here are the ones in uv.lock.

.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install fmt lint typecheck test check docs docs-serve changelog clean

help: ## List the available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install every dependency group and extra, plus the git hooks
	$(UV) sync --all-groups --all-extras
	$(UV) run pre-commit install --hook-type pre-commit --hook-type commit-msg

fmt: ## Format the code and apply safe lint fixes
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

lint: ## Check formatting and lint rules
	$(UV) run ruff format --check .
	$(UV) run ruff check .

typecheck: ## Type-check (strict for src/)
	$(UV) run pyright

test: ## Run the tests with the 100% branch-coverage gate
	$(UV) run pytest --cov --cov-report=term-missing

check: lint typecheck test ## Run everything CI runs

docs: changelog ## Build the documentation site, changelog included, in strict mode, and check its lists rendered, as the Docs workflow does
	$(UV) run zensical build --strict --clean
	$(UV) run python scripts/check_site.py site

docs-serve: ## Serve the documentation site with live reload at http://localhost:8000
	$(UV) run zensical serve

changelog: ## Regenerate CHANGELOG.md from conventional commits
	$(UV) run git-cliff --output CHANGELOG.md
	@$(UV) run python -c "import pathlib; p = pathlib.Path('CHANGELOG.md'); p.write_text(p.read_text().rstrip() + '\n')"

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache .coverage coverage.xml htmlcov dist site .cache
	find . -name __pycache__ -type d -prune -not -path './.venv/*' -exec rm -rf {} +
