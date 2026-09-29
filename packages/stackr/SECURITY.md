# Security policy

## Supported versions

stackr is pre-release (0.x). Security fixes are made on `main` and released in the next version. Once 1.0 ships, the latest minor release receives fixes.

## Reporting a vulnerability

Please do not open a public issue. Report vulnerabilities privately through GitHub's [private vulnerability reporting](https://github.com/alexnodeland/stackr/security/advisories/new).

Include what you can of:

- the affected area (a profile or service, a script, the application template) and commit
- a description of the issue and its impact
- steps to reproduce, or a proof of concept

You can expect an acknowledgement within a week. Once a fix is available, we will publish an advisory crediting you, unless you prefer otherwise.

## Scope notes

stackr's defaults are for local development and single hosts. Published ports bind to `127.0.0.1` unless `STACKR_BIND` says otherwise, and secrets are generated on each machine into a gitignored `.env`. A default that exposes a service beyond the host, a committed secret, or a script that leaks a secret into logs or process listings is a vulnerability.

Vulnerabilities in the services themselves (Supabase, LiteLLM, Langfuse, Grafana and the others) belong with those projects. Tell us as well when stackr's configuration makes one worse, or when a pinned image needs an update.
