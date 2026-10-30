#!/usr/bin/env bash
# Installs proto, then moon, uv, Bun, OpenTofu and TFLint at the versions in .prototools, then the workspaces, as
# `make install` does, without assuming make is in the base image.
set -euo pipefail

curl -fsSL https://moonrepo.dev/install/proto.sh | bash -s -- --yes
export PATH="$HOME/.proto/bin:$HOME/.proto/shims:$PATH"
# Its plugins for OpenTofu and TFLint load only from a trusted file.
proto trust .prototools
proto install
uv python install 3.12 3.13 3.14
uv sync --all-packages --all-groups --all-extras
scripts/bun-install
(cd packages/portalr/web/ui && bun x --bun --no-install playwright install --with-deps --only-shell chromium)
uv run prek install
