# Reference

One page for each area of stackr's configuration. The tables on these pages are generated from the files they describe by `scripts/docs-reference`, and `moon run stackr:reference`, which CI runs, fails when a page no longer matches its file, so what you read here is what the files say. Each page also includes its file in full.

| Page | Describes | Generated from |
|---|---|---|
| [Compose services and profiles](compose.md) | Every service, its profile, image, ports, networks, volumes and health check | `compose.yaml`, `.env.example` |
| [Settings in .env](settings.md) | Every setting, and what `make env` writes for it | `.env.example` |
| [Collector pipelines](collector.md) | The Collector's receivers, processors, exporters and pipelines | `deploy/otel-collector/config.yaml` |
| [Grafana provisioning](grafana.md) | Data sources, the links between signals, and the dashboards | `deploy/grafana/` |
| [LiteLLM configuration](litellm.md) | Models, fallbacks, guardrails and the proxy's settings | `deploy/litellm/config.yaml` |
| [Template questions](template.md) | The application template's questions, and the files each answer generates | `copier.yml`, `template/` |
| [Makefile targets](makefile.md) | Every `make` command, and the variables they read | `Makefile` |
| [Pinned versions](versions.md) | What stackr pins outside `compose.yaml`, and where each pin lives | `versions.env`, `copier.yml` |

Images are named without their versions: `compose.yaml` pins them, and Renovate proposes their updates. To regenerate the pages after changing one of these files, run `make docs-reference`.
