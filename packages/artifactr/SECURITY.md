# Security policy

## Supported versions

artifactr is in alpha (0.x). Security fixes are made on `main` and released in the next version. Once 1.0 ships, the latest minor release receives fixes.

## Reporting a vulnerability

Please do not open a public issue. Report vulnerabilities privately through GitHub's [private vulnerability reporting](https://github.com/alexnodeland/artifactr/security/advisories/new).

Include what you can of:

- the affected package (`core`, `workspace`, `agent`, `sql`, `fastapi`, `mcp`) and version or commit
- a description of the issue and its impact
- steps to reproduce, or a proof of concept

You can expect an acknowledgement within a week. Once a fix is available, we will publish an advisory crediting you, unless you prefer otherwise.

## Scope notes

artifactr enforces tenant isolation through scoped workspace handles ([ADR-0011][adr-0011]). Any way to read or write another tenant's data through the public API is a vulnerability. Authentication itself is the host application's responsibility, through the `resolve_actor` hook.

<!-- Link targets live here so the documentation site can redefine them for its own layout. -->

[adr-0011]: docs/adr/0011-workspace-scoped-artifacts-and-tenant-handles.md
