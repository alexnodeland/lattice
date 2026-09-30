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

**stackr**'s defaults are for local development and single hosts. Published ports bind to `127.0.0.1` unless `STACKR_BIND` says otherwise, and secrets are generated on each machine into a gitignored `.env`. A default that exposes a service beyond the host, a committed secret, or a script that leaks a secret into logs or process listings is a vulnerability.

Local Supabase is the known exception. Its CLI publishes its ports (54321 to 54327) on every interface, with Supabase's well-known local development keys and the fixed database password `postgres`. On a machine reachable from a network you don't trust, block those ports with a firewall, or use the plain PostgreSQL adapter (`STACKR_DATABASE=postgres`).

Vulnerabilities in the services themselves (Supabase, LiteLLM, Langfuse, Grafana and the others) belong with those projects. Tell us as well when stackr's configuration makes one worse, or when a pinned image needs an update.

<!-- Link targets live here so the documentation site can redefine them for its own layout. -->

[artifactr-adr-0011]: docs/artifactr/adr/0011-workspace-scoped-artifacts-and-tenant-handles.md
[reflexr-adr-0016]: docs/reflexr/adr/0016-tenants-and-workspaces-like-artifactr.md
