# AGENTS.md: artifactr.files

[artifactr's AGENTS.md](../../../AGENTS.md) applies; this adds the rules of native files, the `files` extra. Design: [docs/artifactr/files/architecture.md](../../../../../docs/artifactr/files/architecture.md), with its own [ADRs](../../../../../docs/artifactr/files/adr/).

## Layering

`tests/files/test_layering.py` enforces it, and `tests/test_layering.py` holds the rest of artifactr to importing nothing of `artifactr.files`.

- Import the rest of artifactr only from `artifactr.core` and `artifactr.workspace`, by names in their `__all__`; only `tools` may import the agent's.
- `manifest` knows no other layer; only `sql` knows SQL; `fastapi` imports every layer but `sql` and `tools`.
- An app's adapter (`wordcraft/`, `gridcraft/`, ...) imports `manifest`, `app`, `craft` and its own package only.
- `freecad/console/script.py` and `blender/console/script.py` run inside the apps' own interpreters; they are excluded from coverage and may import only those apps' modules.

## Adding or changing a crafting app

- Declare it once in `craft/` (`CRAFTS`) on an existing dialect ([ADR-0009](../../../../../docs/artifactr/files/adr/0009-each-crafting-app-declared-once-on-one-of-two-dialects.md)), and add its layer to `LAYERS` in the layering test.
- Its CLI is pinned by checksum in the root `scripts/crafts/<app>.sha256`; `scripts/craft <app> cli` fetches it.
- Live tests carry `@pytest.mark.craft("<app>")` and run with `CRAFT=<app> moon run artifactr:fidelity`; pull requests run only the fakes (`FakeApp`).
- Corpus files live in `tests/files/corpus/`.

## Pitfalls

- Files are hostile: tell a format by its bytes, never its name, and refuse a FreeCAD or Blender file that may run Python before the app starts ([ADR-0014](../../../../../docs/artifactr/files/adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md), [ADR-0015](../../../../../docs/artifactr/files/adr/0015-blender-on-the-script-dialect-and-no-file-that-may-run-python.md)).
- Its tables have their own migrations in `sql/migrations/versions/`, apart from artifactr's.
- A changed route regenerates `schemas/artifactr-files.openapi.json` (`moon run artifactr:schema`).
