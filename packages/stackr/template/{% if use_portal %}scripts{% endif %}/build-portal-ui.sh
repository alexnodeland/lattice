#!/usr/bin/env bash
# Builds portalr's two UIs, app and admin, from the repository and commit uv.lock pins portalr at.
#
# portalr's wheel carries its UIs, which Vite builds; an install from lattice's repository
# (pyproject.toml) has none. Set PORTAL_UI_DIR to the directory this writes, and the application
# serves them. The Dockerfile runs it; `make portal-ui` does on this machine, which needs git and
# Bun. The commit is read from uv.lock, the one place that says which portalr is installed, so
# the UIs are always the installed router's own.
#
# Usage: scripts/build-portal-ui.sh DIR [UV_LOCK]
#        scripts/build-portal-ui.sh --print [UV_LOCK]    only say the repository and the commit
#   DIR       where to write app/ and admin/
#   UV_LOCK   the lock file (default: uv.lock)

set -euo pipefail

print_only=0
if [[ ${1:-} == --print ]]; then
  print_only=1
  shift
else
  dir=${1:?usage: build-portal-ui.sh DIR [UV_LOCK]}
  shift
fi
lock=${1:-uv.lock}

# The lock's entry for portalr, up to the next package's:
# `source = { git = "https://host/owner/repo?subdirectory=packages%2Fportalr&rev=X#SHA" }`.
# The repository and the commit are both read from it, so a fork's UIs aren't built from another repository.
source=$(awk '/^\[\[package\]\]/ { name = ""; next }
  /^name = / { name = $0 }
  name == "name = \"portalr\"" && /^source = / { print; exit }' "$lock")
repo=$(sed -nE 's/.*git = "([^"?#]+)[?#"].*/\1/p' <<<"$source")
rev=$(sed -nE 's/.*#([0-9a-f]{40})".*/\1/p' <<<"$source")
[[ -n $repo && -n $rev ]] || { echo "build-portal-ui: $lock pins portalr at no git commit" >&2; exit 1; }
if [[ $print_only == 1 ]]; then
  echo "$repo $rev"
  exit 0
fi

out=$(mkdir -p "$dir" && cd "$dir" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git init --quiet "$work/lattice"
cd "$work/lattice"
git remote add origin "$repo"
git fetch --quiet --depth 1 origin "$rev"
git checkout --quiet FETCH_HEAD
bun install --frozen-lockfile --filter '@portalr/app' --filter '@portalr/admin'
for ui in app admin; do
  (cd "packages/portalr/web/$ui" && bun x --bun --no-install vite build --outDir "$out/$ui" --emptyOutDir)
done
# app's build writes mini apps' sandbox page beside portalr's own static files: SandboxOrigin
# serves it from the same directory as the UIs.
rm -rf "$out/sandbox"
cp -R packages/portalr/src/portalr/static/sandbox "$out/sandbox"
