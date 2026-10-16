#!/usr/bin/env bash
# Builds portalr's two UIs, app and admin, from lattice at a commit, into a directory.
#
# portalr's wheel carries its UIs, which Vite builds; an install from lattice's repository
# (pyproject.toml) has none. Set PORTAL_UI_DIR to the directory this writes, and the application
# serves them. The Dockerfile runs it; `make portal-ui` does on this machine, which needs git and
# Bun.
#
# Usage: scripts/build-portal-ui.sh REV DIR
#   REV   the lattice commit pyproject.toml pins portalr at
#   DIR   where to write app/ and admin/

set -euo pipefail

rev=${1:?usage: build-portal-ui.sh REV DIR}
out=$(mkdir -p "${2:?usage: build-portal-ui.sh REV DIR}" && cd "$2" && pwd)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git init --quiet "$work/lattice"
cd "$work/lattice"
git remote add origin https://github.com/alexnodeland/lattice
git fetch --quiet --depth 1 origin "$rev"
git checkout --quiet FETCH_HEAD
bun install --frozen-lockfile
for ui in app admin; do
  (cd "packages/portalr/web/$ui" && bun x --bun --no-install vite build --outDir "$out/$ui" --emptyOutDir)
done
