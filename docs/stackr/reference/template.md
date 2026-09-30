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
| `python_version` | str | `3.12` | `3.12`, `3.13`, `3.14` | always | The Python version it runs on |
| `app_port` | int | `8800` |  | always | The port it is published on, on this machine |

<!-- end generated -->

Copier checks each answer: the name can't be empty; the slug is lowercase letters, digits and single dashes, starting with a letter, at most 30 characters, and not one of the libraries' names (`artifactr`, `artifactr-ai`, `reflexr`, `evalr`), which its package would shadow; and the port is from 1024 to 65535.

## Derived values

These are computed from the answers, or fixed by the template, as the libraries' revisions are ([ADR-0013](../adr/0013-how-the-template-pins-the-libraries.md)). They are never asked, and not recorded in `.copier-answers.yml`, so `copier update` moves them with the template.

<!-- generated: template-derived -->

| Value | Type | Derived as |
|---|---|---|
| `artifactr_rev` | str | `1a635ecb9800c2e414221e7293e8a2de2fdb600c` |
| `reflexr_rev` | str | `dc2d05916cd6d1bf36b7c2b26e29663dfdddc338` |
| `package_name` | str | `{{ project_slug | replace('-', '_') }}` |
| `use_artifactr` | bool | `{{ libraries in ['artifactr', 'both'] }}` |
| `use_reflexr` | bool | `{{ libraries in ['reflexr', 'both'] }}` |

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
| `src/<package>/scores.py` | always | rendered |
| `src/<package>/settings.py` | always | rendered |
| `src/<package>/telemetry.py` | always | rendered |
| `src/<package>/collaboration.py` | `use_artifactr` | rendered |
| `src/<package>/notes.py` | `use_artifactr` | rendered |
| `src/<package>/automation.py` | `use_reflexr` | rendered |
| `src/<package>/tickets.py` | `use_reflexr` | rendered |
| `stackr.env` | always | copied |
| `tests/conftest.py` | always | rendered |
| `tests/test_app.py` | always | rendered |
| `tests/test_auth.py` | always | rendered |
| `tests/test_scores.py` | always | rendered |
| `tests/test_settings.py` | always | rendered |
| `tests/test_evals.py` | `evals` | rendered |
| `tests/test_collaboration.py` | `use_artifactr` | rendered |
| `tests/test_automation.py` | `use_reflexr` | rendered |
| `evals/__init__.py` | `evals` | copied |
| `evals/__main__.py` | `evals` | copied |
| `evals/experiments.py` | `evals` | rendered |

<!-- end generated -->

## The file

??? example "The whole file: `copier.yml`"

    ```yaml
    --8<-- "packages/stackr/copier.yml"
    ```
