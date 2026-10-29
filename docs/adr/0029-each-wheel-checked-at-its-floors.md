# ADR-0029: Each wheel checked at its floors

**Status:** Accepted
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

## Context

The v0.2 release audit found floors below what the code needs.

- artifactr, grantr and portalr import `lattice_core.integrations`, and artifactr and grantr `lattice_core.settings` too (since [ADR-0030](0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)), neither of which `lattice-core-ai` 0.1.0 has, but allow `>=0.1.0`.
- relayr allows `artifactr-ai>=0.2.0`.
- Checking found one more: artifactr and relayr allow `pydantic-ai-slim>=2.51`, but artifactr's runner imports `repair_messages`, which is new in 2.53.

Nothing caught these. CI installs the workspace from its lock, at the newest versions, and `scripts/standalone.py` installs each wheel beside its siblings' wheels from the same commit. A user who installs a package beside an older sibling from PyPI meets the floor; CI never did.

## Decision

- **CI's "Floors (lowest direct)" job installs each wheel at the lowest versions its ranges allow:** `uv pip install --resolution lowest-direct --no-sources`, with every extra it declares, its siblings from PyPI rather than the workspace. Then it imports every module, as `scripts/standalone.py` does (`scripts/lowest_direct.py`).
- **The floors known to be too low are a list, `EXPECTED`,** each with why and what its import says when it fails so, such as `No module named 'artifactr.excalidraw'`. A package on it must still fail with that message. One that fails otherwise, or starts passing, fails the job until the list is right. Every other package must pass. So the job is required, and green, today.
- **An install that fails is never a floor's fault the list names:** when PyPI can't be reached, or nothing satisfies the ranges, the job fails and says the package couldn't be installed, whatever `EXPECTED` says. A re-run settles an outage.
- **Only direct dependencies are at their floors.** Everything else resolves to its newest version that fits, as a user's install would, so a third party's new release can change the result between runs. Pinning the transitive versions would test an install no user makes.
- **Raising a floor stays each package's release step,** the owner's. This changes no floor. Each release that raises one takes its package off `EXPECTED` in the same pull request.

## Options considered

- **An allowed failure** (`continue-on-error`): it would be green whether a floor is right or wrong, and a new floor problem would hide behind the known ones.
- **Lowest everything** (`--resolution lowest`): it would check every transitive floor too, which lattice doesn't set, and would fail on third parties' own floors.

## Consequences

- Easier: a floor that is too low fails a pull request, not a user's install.
- Known: artifactr failed on a lattice-core module 0.1.0 lacks before it reached `repair_messages`, so its `pydantic-ai-slim` floor showed only once its `lattice-core-ai` floor was raised. Both were raised together (2026-10-29: `lattice-core-ai>=0.2.0`, `pydantic-ai-slim>=2.53`, for artifactr and relayr), and artifactr, grantr and portalr came off `EXPECTED`. relayr stays on it until its `artifactr-ai` floor names a release with `artifactr.excalidraw`.
- Harder: CI installs each wheel once more, about a minute in all; and a release must edit `EXPECTED` when it raises a floor.
