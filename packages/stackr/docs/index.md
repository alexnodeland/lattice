---
title: stackr
description: The infrastructure template for applications on artifactr, reflexr and evalr, with an application template that starts them wired to it.
hide:
  - navigation
---

<div class="stackr-hero" markdown>

<h1 class="stackr-visually-hidden">stackr</h1>

![stackr](assets/brand/lockup-light.svg#gh-light-mode-only)
![stackr](assets/brand/lockup-dark.svg#gh-dark-mode-only)

The infrastructure template for applications built on artifactr, reflexr and evalr: local Supabase, the LiteLLM gateway, OpenTelemetry, Grafana's LGTM stack with Pyroscope, and Langfuse, with an application template that starts wired to all of them.

</div>

!!! note "Pre-release"

    stackr v0.1 is built, as planned in [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and has no release yet. The site describes `main`.

## Why: one stack the family's applications share

Every application on [artifactr](https://github.com/alexnodeland/artifactr), [reflexr](https://github.com/alexnodeland/reflexr) or [evalr](https://github.com/alexnodeland/evalr) needs the same infrastructure: a database with sign-in, a gateway in front of the models with budgets and guardrails, traces, metrics, logs and profiles, and a place for LLM traces, scores and datasets. The libraries emit OpenTelemetry, reach models through a LiteLLM proxy and ship their own Grafana dashboards, but those only pay off when something is set up to receive them.

stackr is that setup, in two parts:

- **The stack:** one Docker Compose project with profiles, beside local Supabase, so a laptop or a single host runs what a task needs and nothing more.
- **The application template:** a [Copier](https://copier.readthedocs.io) template that generates an application on artifactr, reflexr or both, already signed in with Supabase, on its PostgreSQL, traced end to end through the gateway, and scored in Langfuse.

Applications talk to **ports**, never to vendors: OTLP to the Collector, the OpenAI API to the gateway, a PostgreSQL URL, JWTs verified against a key set, Langfuse's API for scores. Behind each port is an adapter that stackr configures, so moving an application from the local stack to hosted services changes its settings, not its code ([ADR-0005](adr/0005-ports-and-adapters-for-the-stack.md)).

## A short example

```bash
git clone https://github.com/alexnodeland/stackr.git
cd stackr
make env        # .env, with local secrets generated
make up         # the default profiles, with local Supabase
make smoke      # send test telemetry through the stack and find it where it lands
```

Then generate an application beside it:

```bash
uvx copier copy gh:alexnodeland/stackr my-app
cd my-app && git init
make install && make env && make check
make up         # the application in its app profile, at http://localhost:8800
```

[Getting started](getting-started.md) takes the same path step by step, with what to fill in along the way.

## What you get

- **Profiles as adapter sets.** `observability`, `langfuse` and `gateway` start by default; `make up PROFILES=observability` starts only the Collector, its backends and Grafana. [The stack and its profiles](guides/stack.md)
- **Local Supabase as the database.** Started through its CLI when a profile needs PostgreSQL, with plain PostgreSQL as the alternative behind one setting. [Local Supabase](guides/supabase.md)
- **An LLM gateway.** Model groups with fallbacks across providers, a team and a budget per tenant, and guardrails chosen per request. [The LLM gateway](guides/gateway.md)
- **One route for telemetry.** The OpenTelemetry Collector sends traces to Tempo and Langfuse, metrics to Prometheus and logs to Loki, and Grafana links them to each other and to Pyroscope's profiles. [Observability](guides/observability.md)
- **Self-hosted Langfuse.** Traces arrive through the Collector; applications use Langfuse's API only for scores and datasets. [Langfuse](guides/langfuse.md)
- **An application template.** FastAPI with each library's REST, WebSocket and MCP surfaces, examples, evals, a dev container and the family's quality gates. [The application template](guides/template.md)
- **Checked every way it can be.** `make validate` checks every configuration with each service's own validator, and the smoke tests start the stack and follow telemetry, a gateway request and an application's agents to where they land. [Validation and CI](guides/validation.md)
- **Local by default.** Secrets are generated into a gitignored `.env`, and every published port binds to `127.0.0.1`. [Security](guides/security.md)

## Where to go next

| If you want to | Read |
|---|---|
| Run the stack now | [Getting started](getting-started.md) |
| Understand one part in depth | The [guides](guides/stack.md) |
| Look up a service, setting, port or command | The [reference](reference/index.md) |
| Understand why it is built this way | The [architecture](architecture.md) and the [decision records](adr/README.md) |
| Fix something that doesn't start | [Troubleshooting](guides/troubleshooting.md) |
| Contribute | [Contributing](project/contributing.md) |
