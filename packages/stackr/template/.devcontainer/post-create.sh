#!/usr/bin/env bash
set -euo pipefail

# Same as `make install`, without assuming make is present in the base image. Without a git
# repository it skips the hooks, rather than fail the container: run `git init`, then
# `make install`.
uv sync --all-groups
if git rev-parse --git-dir >/dev/null 2>&1; then
  uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
else
  echo "post-create: no git repository here, so no git hooks; run git init, then make install" >&2
fi
