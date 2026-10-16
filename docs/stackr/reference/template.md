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
| `access` | str | `grantr` | `grantr`, `none` | always | Who may do what |
| `portal` | bool | yes |  | `access == 'grantr'` | Include portalr (an app UI to chat with the agents and see their work, and an admin UI for access, feedback, traces and spend)? It signs people in through a Supabase project, which the application is told of in PORTAL_SUPABASE_URL and PORTAL_SUPABASE_KEY: without one it is off. It adds a Bun build and a network fetch to the image. |
| `hosting` | str | `none` | `none`, `host` | always | Where it is hosted, beside stackr's recipe for it (stackr RFC-0004) |
| `python_version` | str | `3.12` | `3.12`, `3.13`, `3.14` | always | The Python version it runs on |
| `app_port` | int | `8800` |  | always | The port it is published on, on this machine |

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
| `src/<package>/notes.py` | `use_artifactr` | rendered |
| `src/<package>/portal.py` | `use_portal` | rendered |
| `src/<package>/automation.py` | `use_reflexr` | rendered |
| `src/<package>/tickets.py` | `use_reflexr` | rendered |
| `src/<package>/bridge.py` | `use_relayr` | rendered |
| `src/<package>/chat_rules.py` | `use_relayr` | rendered |
| `src/<package>/incidents.py` | `use_relayr` | rendered |
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
| `tests/test_portal.py` | `use_portal` | rendered |
| `tests/test_automation.py` | `use_reflexr` | rendered |
| `tests/test_bridge.py` | `use_relayr` | rendered |
| `tests/test_chat_rules.py` | `use_relayr` | rendered |
| `access.md` | `access == 'grantr'` | rendered |
| `evals/__init__.py` | `evals` | copied |
| `evals/__main__.py` | `evals` | copied |
| `evals/experiments.py` | `evals` | rendered |
| `deploy/host/compose.prod.yaml` | `hosting == 'host'` | rendered |
| `scripts/build-portal-ui.sh` | `use_portal` | copied |

<!-- end generated -->

## The file

??? example "The whole file: `copier.yml`"

    ```yaml
    --8<-- "packages/stackr/copier.yml"
    ```
