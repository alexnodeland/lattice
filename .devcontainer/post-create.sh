#!/usr/bin/env bash
# Installs proto, then moon and uv at the versions in .prototools, then the workspace, as
# `make install` does, without assuming make is in the base image.
set -euo pipefail

curl -fsSL https://moonrepo.dev/install/proto.sh | bash -s -- --yes
export PATH="$HOME/.proto/bin:$HOME/.proto/shims:$PATH"
proto install
uv python install 3.12 3.13 3.14
uv sync --all-packages --all-groups --all-extras
uv run prek install
