---
name: check-change
description: Check a change in lattice the way CI will, running the checks of only the projects it affects and of the projects that depend on them. Use before declaring work done, before committing or opening a PR, or when asked to "run the checks" or "make sure CI passes".
---

# Check a change as CI does

CI runs each task in every project a change touches, and in every project that depends on one, through `scripts/affected.py`. Do the same locally rather than `make check`, which runs everything.

1. **Format first:** `moon run <project>:format` for each project you edited (the edit hook has done each file, but not files changed by other means).
2. **Run the affected checks** against `main`:

   ```bash
   MOON_BASE=origin/main MOON_HEAD=HEAD uv run python scripts/affected.py check
   ```

   It names each project it runs. For a quick loop on one project, `moon run <project>:check`, or `moon run <project>:test` alone.
3. **If a generated file drifted,** use the `regenerate` skill.
4. **If the public API changed,** `moon run lattice:breaks`. A break needs `!` in the PR title and a `BREAKING CHANGE:` footer.
5. **Docs changed?** `moon run lattice:docs` (strict, and it checks that lists rendered).

What `check` doesn't run locally needs Docker and runs in CI's Acceptance and Images jobs: `<pkg>:test-pg`, `<pkg>:api`, `app:bdd`, `<example>:image`. Run one only when the change is in what it covers, and say which you ran.

Report what ran and what failed, with the output. A failing test that only fails in some orders is reproduced with `uv run pytest --randomly-seed=N` (the seed is printed at the top of the run).
