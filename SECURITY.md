# Security policy

## Supported versions

Every package in lattice is pre-release (0.x). Security fixes are made on `main` and released in the package's next version. Once a package ships 1.0, its latest minor release receives fixes.

## Reporting a vulnerability

Please do not open a public issue. Report vulnerabilities privately through GitHub's [private vulnerability reporting](https://github.com/alexnodeland/lattice/security/advisories/new).

Include what you can of:

- the affected package and module (such as artifactr's `workspace` or evalr's `langfuse`), or for stackr the area (a profile or service, a script, the application template), and its version or commit
- a description of the issue and its impact
- steps to reproduce, or a proof of concept

You can expect an acknowledgement within a week. Once a fix is available, we will publish an advisory crediting you, unless you prefer otherwise.

## Scope notes

**artifactr** enforces tenant isolation through scoped workspace handles ([artifactr ADR-0011][artifactr-adr-0011]). Any way to read or write another tenant's data through the public API is a vulnerability. Authentication itself is the host application's responsibility, through the `resolve_actor` hook.

**reflexr** enforces tenant isolation through scoped workspace handles ([reflexr ADR-0016][reflexr-adr-0016]). Any way to read or write another tenant's workspaces through the public API is a vulnerability, as is any way for event data to reach a query other than as a bound parameter. Authentication itself is the host application's responsibility, through the `resolve_actor` hook.

**evalr** reads the inputs it judges (threads, runs, artifacts) and sends them to the evaluators the application configures: a language model, TypeSafe's API, Langfuse or the Hugging Face Hub. Any way for evalr to send data somewhere the application did not configure is a vulnerability, as is loading a saved judge or dataset in a way that executes code from it, or a dataset name that makes a store read or write outside its root. API keys are the application's to supply; evalr never logs them or records them on spans.

**grantr** decides who may do what, for artifactr, reflexr and portalr, and keeps the record of it ([grantr ADR-0001][grantr-adr-0001]). Any way for a command or read to succeed that its subject's roles and grants do not allow is a vulnerability, as is any way to give oneself more access than the roles one holds allow ([grantr ADR-0010][grantr-adr-0010]), to pass a service principal's id for a library's own actor ([ADR-0028][grantr-adr-0028]), to change access without an entry in the audit log, or to read or write another tenant's rows through its SQL storage, whether by its scoping or by defeating its row-level security, which is the second line of defence ([ADR-0026][grantr-adr-0026]). A check that fails open is the same. How a person or an API key becomes a subject is the host application's, through the `resolve_actor` hook.

**relayr** carries events from artifactr to reflexr and acts for reflexr's rules in artifactr, and what it may do there is bounded by each rule's allowlist and the actors' roles ([relayr ADR-0020][relayr-adr-0020], [ADR-0017][relayr-adr-0017]). Any way for a rule to write, start a turn or open a thread its allowlist does not allow, to carry an event into a tenant other than the one it came from, or to read or write another tenant's ledger, whether by its scoping or by defeating its row-level security, which is the second line of defence ([ADR-0027][relayr-adr-0027]), is a vulnerability.

**portalr** serves two UIs and a router of reads of the tools that watch the application: Tempo, Loki, Prometheus, Langfuse and LiteLLM. It also invites people by email, creates tenants, and runs Retry, Skip and Cancel on rules' runs. It asks grantr to allow each read and each of those, and makes each for the caller's tenant ([portalr ADR-0011][portalr-adr-0011]). Any way to read another tenant's traces, logs, metrics, scores or spend, to read what a read is meant to withhold (the attributes and lines of traces and logs are given only when asked for, one at a time: [ADR-0030][portalr-adr-0030], [ADR-0031][portalr-adr-0031]), to invite, create or run something grantr does not allow, or to make the router send a request to a tool for something the caller was not allowed is a vulnerability, as is a script injected into the UIs, which carry a strict Content-Security-Policy. Sign-in is the application's Supabase Auth.

**lattice-core** holds what the libraries must keep identical, and nothing for applications to import: they re-export it. A vulnerability in it is one in each package that does. These are: a span or log record that carries another tenant's id, or none where its tenant is known (`lattice_core.otel`); `redact_access_token` leaving an `access_token` parameter's value in a URL, a query or a path; the tenant-workspace tag (`workspace_tag`, `parse_workspace_tag`, `request_tags`) encoding two different tenants' or workspaces' ids as one tag, which files spend under the wrong tenant ([lattice ADR-0019][lattice-adr-0019]); and a row-level-security helper (`TenantSession`, `tenant_policy`, `grant`) that lets a transaction see, change or add another tenant's rows, or one that names no tenant see any. Report it here, whichever package you met it through.

**stackr**'s defaults are for local development and single hosts. Published ports bind to `127.0.0.1` unless `STACKR_BIND` says otherwise, and secrets are generated on each machine into a gitignored `.env`. A default that exposes a service beyond the host, a committed secret, or a script that leaks a secret into logs or process listings is a vulnerability.

Local Supabase is the known exception. Its CLI publishes its ports (54321 to 54327) on every interface, with Supabase's well-known local development keys and the fixed database password `postgres`. On a machine reachable from a network you don't trust, block those ports with a firewall, or use the plain PostgreSQL adapter (`STACKR_DATABASE=postgres`).

Vulnerabilities in the services themselves (Supabase, LiteLLM, Langfuse, Grafana and the others) belong with those projects. Tell us as well when stackr's configuration makes one worse, or when a pinned image needs an update.

<!-- Link targets live here so the documentation site can redefine them for its own layout. -->

[artifactr-adr-0011]: docs/artifactr/adr/0011-workspace-scoped-artifacts-and-tenant-handles.md
[reflexr-adr-0016]: docs/reflexr/adr/0016-tenants-and-workspaces-like-artifactr.md
[grantr-adr-0001]: docs/grantr/adr/0001-the-hook-hears-the-action.md
[grantr-adr-0010]: docs/grantr/adr/0010-commands-bounded-by-what-their-maker-holds.md
[grantr-adr-0026]: docs/grantr/adr/0026-row-level-security-under-the-scoping.md
[grantr-adr-0028]: docs/grantr/adr/0028-a-principals-id-cant-pass-for-the-libraries-actors.md
[relayr-adr-0017]: docs/relayr/adr/0017-the-follower-acts-as-the-application.md
[relayr-adr-0020]: docs/relayr/adr/0020-allowlists.md
[relayr-adr-0027]: docs/relayr/adr/0027-row-level-security-under-the-scoping.md
[portalr-adr-0011]: docs/portalr/adr/0011-the-router-and-its-readers.md
[portalr-adr-0030]: docs/portalr/adr/0030-traces-and-the-trace-view.md
[portalr-adr-0031]: docs/portalr/adr/0031-logs-and-health.md
[lattice-adr-0019]: docs/adr/0019-a-tag-for-each-tenants-workspace.md
