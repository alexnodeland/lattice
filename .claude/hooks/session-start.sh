#!/usr/bin/env bash
# Puts proto's tools (moon, Bun, uv, from .prototools) on the session's PATH, so `moon run` works
# in a shell that never sourced proto's setup, as a session started from another directory hasn't.
set -euo pipefail

proto_home="${PROTO_HOME:-$HOME/.proto}"
if [[ -n "${CLAUDE_ENV_FILE:-}" && -d "$proto_home" ]]; then
  echo "export PATH=\"$proto_home/shims:$proto_home/bin:\$PATH\"" >>"$CLAUDE_ENV_FILE"
fi
