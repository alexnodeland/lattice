# Template questions

The application template's questions are in stackr's `copier.yml`, which the `copier.yml` at lattice's root includes, and its files in `template/` ([The application template](../guides/template.md)). Answer them interactively, or with `--defaults` and `--data NAME=VALUE`.

## Questions

<!-- generated: template-questions -->

| Question | Type | Default | Choices | Asked when | Help |
|---|---|---|---|---|---|
| `project_name` | str | `My App` |  | always | The application's name, as people read it |
| `project_slug` | str | `{{ project_name.strip().lower() | regex_replace('[^a-z0-9]+', '-') | trim('-') }}` |  | always | Its slug: the Python distribution, the OpenTelemetry service and the Compose project |
| `description` | str | `An application on stackr.` |  | always | One line about what it does |
| `libraries` | str | `both` | `artifactr`, `reflexr`, `both` | always | The libraries it uses |
| `evals` | bool | yes |  | always | Include evaluation with evalr (an evals/ directory and a starter experiment)? |
| `bridge` | bool | yes |  | `libraries == 'both'` | Bridge them with relayr (chats and artifacts become events for rules, and rules' runs act back as proposals and notices; with an incident timeline example)? |
| `tracker` | str | `none` | `none`, `plane`, `vikunja` | `libraries == 'both' and bridge` | A task tracker for relayr (rules' runs file items there, and people's changes come back as events; with a dead-letter example)? It runs beside the stack from stackr's recipe for it, with each tenant provisioned as stackr's tracker guide says. |
| `ui` | bool | yes |  | `libraries in ['artifactr', 'both']` | Include artifactr's forms and dashboards (the agent asks people forms and shows them dashboards in its chat; what they send is checked before it commits and, with the bridge, becomes an event for rules)? |
| `native_files` | bool | yes |  | `libraries in ['artifactr', 'both']` | Include native files (Word, Excel, PowerPoint, PDF, CAD, 3D, image and design files kept as artifacts, each read and edited by its app's pinned CLI in a worker of its own with no route out, and by people in the app's browser build)? No app runs until FILES_CRAFTS names it: `make up FILES="wordcraft gridcraft"`. Each builds an image from its pinned release. |
| `diagrams` | bool | yes |  | `libraries in ['artifactr', 'both'] and native_files` | Include diagrams (Excalidraw's, which the agent draws from Mermaid or shapes and renders, in a worker of its own with no route out: headless Chromium)? They keep their images with native files'. The worker runs only with DIAGRAMS=on: `make up DIAGRAMS=on`. Each workspace switches diagrams on as an integration, off until then. |
| `access` | str | `grantr` | `grantr`, `none` | always | Who may do what |
| `portal` | bool | yes |  | `access == 'grantr'` | Include portalr (an app UI to chat with the agents and see their work, and an admin UI for access, feedback, traces and spend)? It signs people in through a Supabase project, which the application is told of in PORTAL_SUPABASE_URL and PORTAL_SUPABASE_KEY: without one it is off. It adds a Bun build and a network fetch to the image. |
| `hosting` | str | `none` | `none`, `host` | always | Where it is hosted, beside stackr's recipe for it (stackr RFC-0004) |
| `python_version` | str | `3.12` | `3.12`, `3.13`, `3.14` | always | The Python version it runs on |
| `app_port` | int | `8800` |  | always | The port it is published on, on this machine; the next five are its mini apps' and editors' |

<!-- end generated -->

Copier checks each answer: the name can't be empty; the slug is lowercase letters, digits and single dashes, starting with a letter, at most 30 characters, and not one of the libraries' names (`artifactr`, `artifactr-ai`, `reflexr`, `evalr`), which its package would shadow; and the port is from 1024 to 65535.

## Derived values

These are computed from the answers, apart from `libraries_path`, which `scripts/check-app`, CI's Template job, sets to lattice's `packages/` directory so that a generated application installs the libraries from the checkout ([ADR-0018](../adr/0018-the-template-pins-the-libraries-at-its-own-commit.md)). They are never asked, and not recorded in `.copier-answers.yml`.

<!-- generated: template-derived -->

| Value | Type | Derived as |
|---|---|---|
| `libraries_path` | str | empty |
| `package_name` | str | `{{ project_slug | replace('-', '_') }}` |
| `use_artifactr` | bool | `{{ libraries in ['artifactr', 'both'] }}` |
| `use_reflexr` | bool | `{{ libraries in ['reflexr', 'both'] }}` |
| `use_relayr` | bool | `{{ libraries == 'both' and bridge }}` |
| `use_tracker` | bool | `{{ libraries == 'both' and bridge and tracker != 'none' }}` |
| `use_ui` | bool | `{{ libraries in ['artifactr', 'both'] and ui }}` |
| `use_files` | bool | `{{ libraries in ['artifactr', 'both'] and native_files }}` |
| `use_diagrams` | bool | `{{ use_files and diagrams }}` |
| `use_integrations` | bool | `{{ use_ui or use_files or use_tracker }}` |
| `crafts` | yaml | `{'wordcraft': {'version': '0.11.0', 'type': 'WordDocument', 'editor': 5}, 'gridcraft': {'version': '0.8.0', 'type': 'Workbook', 'editor': 2}, 'deckcraft': {'version': '0.7.0', 'type': 'Presentation', 'no_editor': 'no host bridge'}, 'pdfcraft': {'version': '0.8.0', 'type': 'PdfDocument', 'editor': 3}, 'cadcraft': {'version': '0.8.0', 'type': 'Drawing', 'editor': 4}, 'photocraft': {'version': '0.9.0', 'type': 'LayeredImage', 'no_editor': 'no host bridge'}, 'vectorcraft': {'version': '0.12.0', 'type': 'VectorImage', 'no_editor': 'no host bridge'}, 'designcraft': {'version': '0.9.0', 'type': 'PageLayout', 'no_editor': 'no host bridge'}, 'figcraft': {'version': '0.6.0', 'type': 'Design', 'no_editor': 'no host bridge'}, 'filmcraft': {'version': '0.8.0', 'type': 'VideoProject', 'no_editor': 'no host bridge'}, 'effectcraft': {'version': '0.11.1', 'type': 'MotionGraphics', 'no_editor': 'no host bridge'}, 'soundcraft': {'version': '0.8.0', 'type': 'AudioSession', 'no_editor': 'no host bridge'}, 'freecad': {'version': '1.1.4', 'type': 'CadModel', 'no_editor': 'no browser build'}, 'blender': {'version': '5.2.2', 'type': 'Scene', 'no_editor': 'no browser build', 'platform': 'linux/amd64', 'memory': 4, 'packages': ['libx11-6', 'libxi6', 'libxxf86vm1', 'libxfixes3', 'libxrender1', 'libxkbcommon0', 'libsm6', 'libice6', 'libgl1', 'libegl1', 'libegl-mesa0', 'libgl1-mesa-dri'], 'source': 'https://download.blender.org/source/blender-5.2.2.tar.xz', 'source_sha256': '56a3b1ec97479ff24dce65d2f09f8a1895005cece279b701fe4fcf74bce3f77e'}}` |
| `use_portal` | bool | `{{ access == 'grantr' and portal }}` |

| Copier setting | Value |
|---|---|
| `_subdirectory` | `template` |
| `_min_copier_version` | `9.4` |
| `_answers_file` | `.copier-answers.yml` |

<!-- end generated -->

## The files it generates

A file whose name ends in `.jinja` in `template/` is rendered with the answers; any other is copied as it is. A name with `{% if ... %}` in it is generated only when its condition holds, and `<package>` is the package's name.

<!-- generated: template-files -->

| File in the application | Generated when | How |
|---|---|---|
| `.copier-answers.yml` | always | rendered |
| `.devcontainer/compose.yaml` | always | rendered |
| `.devcontainer/devcontainer.json` | always | rendered |
| `.devcontainer/initialize.sh` | always | copied |
| `.devcontainer/post-create.sh` | always | copied |
| `.dockerignore` | always | copied |
| `.editorconfig` | always | copied |
| `.env.example` | always | rendered |
| `.github/dependabot.yml` | always | copied |
| `.github/workflows/ci.yml` | always | rendered |
| `.gitignore` | always | copied |
| `.pre-commit-config.yaml` | always | copied |
| `.python-version` | always | rendered |
| `Dockerfile` | always | rendered |
| `Makefile` | always | rendered |
| `README.md` | always | rendered |
| `compose.yaml` | always | rendered |
| `pyproject.toml` | always | rendered |
| `src/<package>/__init__.py` | always | rendered |
| `src/<package>/app.py` | always | rendered |
| `src/<package>/auth.py` | always | rendered |
| `src/<package>/database.py` | always | rendered |
| `src/<package>/gateway.py` | always | rendered |
| `src/<package>/py.typed` | always | copied |
| `src/<package>/redaction.py` | always | rendered |
| `src/<package>/scores.py` | always | rendered |
| `src/<package>/settings.py` | always | rendered |
| `src/<package>/telemetry.py` | always | rendered |
| `src/<package>/access.py` | `access == 'grantr'` | rendered |
| `src/<package>/admin.py` | `access == 'grantr'` | rendered |
| `src/<package>/collaboration.py` | `use_artifactr` | rendered |
| `src/<package>/kinds.py` | `use_artifactr` | rendered |
| `src/<package>/notes.py` | `use_artifactr` | rendered |
| `src/<package>/files.py` | `use_files` | rendered |
| `src/<package>/editor.py` | `use_files and use_portal` | rendered |
| `src/<package>/portal.py` | `use_portal` | rendered |
| `src/<package>/automation.py` | `use_reflexr` | rendered |
| `src/<package>/tickets.py` | `use_reflexr` | rendered |
| `src/<package>/bridge.py` | `use_relayr` | rendered |
| `src/<package>/chat_rules.py` | `use_relayr` | rendered |
| `src/<package>/incidents.py` | `use_relayr` | rendered |
| `src/<package>/tracking.py` | `use_tracker` | rendered |
| `stackr.env` | always | copied |
| `tests/conftest.py` | always | rendered |
| `tests/test_app.py` | always | rendered |
| `tests/test_auth.py` | always | rendered |
| `tests/test_redaction.py` | always | rendered |
| `tests/test_scores.py` | always | rendered |
| `tests/test_settings.py` | always | rendered |
| `tests/test_access.py` | `access == 'grantr'` | rendered |
| `tests/test_admin.py` | `access == 'grantr'` | rendered |
| `tests/test_evals.py` | `evals` | rendered |
| `tests/test_collaboration.py` | `use_artifactr` | rendered |
| `tests/test_kinds.py` | `use_artifactr` | rendered |
| `tests/test_models.py` | `use_artifactr` | rendered |
| `tests/test_diagrams.py` | `use_diagrams` | rendered |
| `tests/test_files.py` | `use_files` | rendered |
| `tests/test_portal.py` | `use_portal` | rendered |
| `tests/test_automation.py` | `use_reflexr` | rendered |
| `tests/test_bridge.py` | `use_relayr` | rendered |
| `tests/test_chat_rules.py` | `use_relayr` | rendered |
| `tests/test_tracking.py` | `use_tracker` | rendered |
| `access.md` | `access == 'grantr'` | rendered |
| `evals/__init__.py` | `evals` | copied |
| `evals/__main__.py` | `evals` | copied |
| `evals/experiments.py` | `evals` | rendered |
| `deploy/host/compose.prod.yaml` | `hosting == 'host'` | rendered |
| `scripts/craft` | `use_files` | copied |
| `scripts/crafts/blender.sha256` | `use_files` | copied |
| `scripts/crafts/cadcraft.sha256` | `use_files` | copied |
| `scripts/crafts/deckcraft.sha256` | `use_files` | copied |
| `scripts/crafts/designcraft.sha256` | `use_files` | copied |
| `scripts/crafts/effectcraft.sha256` | `use_files` | copied |
| `scripts/crafts/figcraft.sha256` | `use_files` | copied |
| `scripts/crafts/filmcraft.sha256` | `use_files` | copied |
| `scripts/crafts/freecad.sha256` | `use_files` | copied |
| `scripts/crafts/gridcraft.sha256` | `use_files` | copied |
| `scripts/crafts/pdfcraft.sha256` | `use_files` | copied |
| `scripts/crafts/photocraft.sha256` | `use_files` | copied |
| `scripts/crafts/soundcraft.sha256` | `use_files` | copied |
| `scripts/crafts/vectorcraft.sha256` | `use_files` | copied |
| `scripts/crafts/wordcraft.sha256` | `use_files` | copied |
| `scripts/build-diagrams-worker.sh` | `use_diagrams` and `use_files` | copied |
| `brand/README.md` | `use_portal` | copied |
| `scripts/build-portal-ui.sh` | `use_portal` | copied |
| `scripts/tailnet.sh` | `use_portal` | copied |

<!-- end generated -->

## The file

??? example "The whole file: `copier.yml`"

    ```yaml
    --8<-- "packages/stackr/copier.yml"
    ```
