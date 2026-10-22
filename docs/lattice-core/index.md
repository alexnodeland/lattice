---
title: lattice-core
description: What lattice's packages share and must keep identical, which each depends on and re-exports.
---

# lattice-core

What lattice's packages share and must keep identical. artifactr, reflexr and grantr import none of one another, and relayr bridges artifactr and reflexr ([reflexr ADR-0003](../reflexr/adr/0003-independent-sibling-of-artifactr.md)). Where two of them would otherwise copy the same code, they depend on lattice-core, which imports no lattice package ([lattice ADR-0018](../adr/0018-lattice-core-what-the-libraries-share.md)).

!!! note "Not for applications"

    An application imports from the package it uses: each re-exports what it makes public from here, so its API is unchanged.

## What it holds

| Module | What | Shared by |
|---|---|---|
| [`lattice_core.schema`](reference.md#lattice_coreschema) | `tag_required`, which makes a union member's tag required in its JSON Schema | artifactr, reflexr |
| [`lattice_core.text`](reference.md#lattice_coretext) | `holds_nul`, which finds a NUL character, which PostgreSQL's text can't store, anywhere in a value | artifactr, reflexr |
| [`lattice_core.sql`](reference.md#lattice_coresql) (the `sql` extra) | `create_sqlite_engine`, whose transactions take turns; `TenantSession`, `tenant_policy` and `grant`, for row-level security; and `to_the_end`, `awaited_to_the_end` and `lock_row`, which await a database call to its end and lock a row | artifactr, reflexr, grantr, relayr |
| [`lattice_core.otel.contribution`](reference.md#lattice_coreotelcontribution) | The contract a library's contribution follows: `Contribution`, `TelemetryContribution`, `MetricsDetail` and `Instrumented` ([ADR-0020](../adr/0020-the-telemetry-contract-needs-no-extra.md)) | artifactr, reflexr, relayr |
| [`lattice_core.otel.configure`](reference.md#lattice_coreotelconfigure) (the `otel` extra) | `configure_telemetry`, `TelemetryHandle` and the contributions it composes, the tenant on every span's records, and `redact_access_token` | artifactr, reflexr |
| [`lattice_core.langfuse`](reference.md#lattice_corelangfuse) (the `langfuse` extra) | `span_filter` and `no_spans`, a Langfuse client's span filters | artifactr, reflexr |
| [`lattice_core.litellm`](reference.md#lattice_corelitellm) (the `litellm` extra) | `litellm_model`, a pydantic-ai model over a LiteLLM proxy's model group, and `add_propagated_tags`, which adds the `rule:` and `kind:` trace tags Langfuse is propagating to a request's ([ADR-0022](../adr/0022-litellm-requests-carry-the-propagated-trace-tags.md)) | artifactr, reflexr |
| [`lattice_core.integrations`](reference.md#lattice_coreintegrations) | `Integrations`, the port every integration asks before it acts in a workspace, `KNOWN`, the registry of lattice's integrations with each one's default and description, and `Defaults`, the answer without a store ([ADR-0027](../adr/0027-integrations-switched-per-workspace-through-one-port.md)) | grantr, artifactr, relayr, portalr |
| [`lattice_core.settings`](reference.md#lattice_coresettings) | `Settings`, the port a package asks for a setting's value each time it acts, `KNOWN_SETTINGS`, lattice's typed settings, each narrowed only below the operator, and `SettingsDefaults`, the answer without a store ([ADR-0030](../adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)) | grantr, artifactr |
| [`lattice_core.tags`](reference.md#lattice_coretags) | `request_tags`, the tags that file a model request's spend under its tenant and workspace, and `workspace_tag` and `parse_workspace_tag`, which write and read the `tenant-workspace:` tag ([ADR-0019](../adr/0019-a-tag-for-each-tenants-workspace.md)) | artifactr, reflexr, portalr |
| [`lattice_core.logs`](reference.md#lattice_corelogs) | `logging_left_alone`, which puts the root logger back as it was | artifactr, reflexr |
| [`lattice_core.refusals`](reference.md#lattice_corerefusals) | `Refused`, `RejectionDetail` and `FieldError`, the body of a refused REST request, and `refusals`, which builds the responses a router documents ([ADR-0021](../adr/0021-the-refusal-schema-needs-no-extra.md)) | artifactr, reflexr, portalr |

That completes the plan in ADR-0018.

## What belongs here

Only infrastructure that is the same in two or more packages, word for word but for their names, and must stay the same. Code that only looks alike stays where it is, and nothing about a package's domain belongs here. lattice-core changes only by addition and deprecation, and each package requires a lower bound of it.

## Installing it

You don't install it yourself: the packages that need it require it. Its distribution is `lattice-core-ai`, since the name `lattice-core` on PyPI is an unrelated project, and it is imported as `lattice_core`. It is on PyPI, from 0.1.0. A package installed from lattice with uv takes it from the same commit; pip takes it from PyPI.
