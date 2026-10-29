#!/usr/bin/env bash
# After an edit, formats the one file and applies safe lint fixes, as `moon run <project>:format`
# would, and tells Claude about an inline suppression, which tests/test_quality.py fails on. It
# touches only the edited file, so it stays fast; `check` remains the full gate.
set -euo pipefail

file="$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')"
[[ -f "$file" ]] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}"

case "$file" in
  *.py)
    uv run --no-sync ruff format --quiet "$file" || true
    uv run --no-sync ruff check --fix --quiet "$file" >/dev/null || true
    if grep -nE '#\s*(type:\s*ignore|pyright:\s*ignore|noqa|pragma:\s*no\s*cover)' "$file" >&2; then
      echo "Inline suppressions fail tests/test_quality.py: restructure the code instead." >&2
      exit 2
    fi
    ;;
  */packages/portalr/web/*.ts | */packages/portalr/web/*.tsx | */packages/portalr/web/*.js | */packages/portalr/web/*.json | */packages/portalr/web/*.css)
    bun x --bun --no-install biome check --write --no-errors-on-unmatched "$file" >/dev/null 2>&1 || true
    if grep -nE '@ts-(ignore|expect-error|nocheck)|biome-ignore' "$file" >&2; then
      echo "Inline suppressions fail tests/test_quality.py: restructure the code instead." >&2
      exit 2
    fi
    ;;
esac
