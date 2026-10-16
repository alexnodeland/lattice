#!/usr/bin/env bash
# Builds portalr's two UIs, app and admin, from lattice at the commit uv.lock pins portalr at.
#
# portalr's wheel carries its UIs, which Vite builds; an install from lattice's repository
# (pyproject.toml) has none. Set PORTAL_UI_DIR to the directory this writes, and the application
# serves them. The Dockerfile runs it; `make portal-ui` does on this machine, which needs git and
# Bun. The commit is read from uv.lock, the one place that says which portalr is installed, so
# the UIs are always the installed router's own.
#
# Usage: scripts/build-portal-ui.sh DIR [UV_LOCK]
#        scripts/build-portal-ui.sh --print-rev [UV_LOCK]    only say the commit
#   DIR       where to write app/ and admin/
#   UV_LOCK   the lock file (default: uv.lock)

set -euo pipefail

if [[ ${1:-} == --print-rev ]]; then
  print_only=1
  shift
else
  print_only=0
fi
dir=${1:-}
[[ $print_only == 1 || -n $dir ]] || { echo "usage: build-portal-ui.sh DIR [UV_LOCK]" >&2; exit 2; }
lock=${2:-uv.lock}
[[ $print_only == 0 ]] || lock=${1:-uv.lock}

# The lock's entry for portalr: `source = { git = "...?subdirectory=packages%2Fportalr&rev=X#SHA" }`.
rev=$(awk '/^name = "portalr"$/ { found = 1 } found && /^source = / { print; exit }' "$lock" |
  sed -nE 's/.*#([0-9a-f]{40}).*/\1/p')
[[ -n $rev ]] || { echo "build-portal-ui: $lock pins portalr at no git commit" >&2; exit 1; }
if [[ $print_only == 1 ]]; then
  echo "$rev"
  exit 0
fi

out=$(mkdir -p "$dir" && cd "$dir" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git init --quiet "$work/lattice"
cd "$work/lattice"
git remote add origin https://github.com/alexnodeland/lattice
git fetch --quiet --depth 1 origin "$rev"
git checkout --quiet FETCH_HEAD
bun install --frozen-lockfile --filter '@portalr/app' --filter '@portalr/admin'
for ui in app admin; do
  (cd "packages/portalr/web/$ui" && bun x --bun --no-install vite build --outDir "$out/$ui" --emptyOutDir)
done
