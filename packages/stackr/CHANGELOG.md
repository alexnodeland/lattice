# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Before lattice]

### Features

- **template**: Move onto the libraries' main, with telemetry set up once and reflexr's names qualified ([#40](https://github.com/alexnodeland/stackr/pull/40)) (**breaking**)
- **template**: Move onto the libraries' main, and stop the reactor gracefully ([#36](https://github.com/alexnodeland/stackr/pull/36))
- **scripts**: Bump the template's library revisions with make bump-libraries ([#32](https://github.com/alexnodeland/stackr/pull/32))
- **template**: Add the Copier application template ([#15](https://github.com/alexnodeland/stackr/pull/15))
- **gateway**: Add the LiteLLM proxy with a team per tenant and guardrails ([#14](https://github.com/alexnodeland/stackr/pull/14))
- **supabase**: Run local Supabase as the default database adapter ([#13](https://github.com/alexnodeland/stackr/pull/13))
- **langfuse**: Add self-hosted Langfuse behind the Collector ([#12](https://github.com/alexnodeland/stackr/pull/12))
- **observability**: Add the Collector, LGTM with Pyroscope, and Grafana ([#11](https://github.com/alexnodeland/stackr/pull/11))

### Bug fixes

- **template**: Pass its own checks under every slug it accepts, and refuse the libraries' names ([#41](https://github.com/alexnodeland/stackr/pull/41))
- Follow STACKR_BIND in create-tenant, and fix what the docs review found ([#33](https://github.com/alexnodeland/stackr/pull/33))
- **deps**: Keep the plain PostgreSQL adapter on local Supabase's major version ([#26](https://github.com/alexnodeland/stackr/pull/26))
- **observability**: Tell Grafana that metrics arrive once a minute ([#19](https://github.com/alexnodeland/stackr/pull/19))
- **template**: Stop the reactor even when it fails as it stops ([#17](https://github.com/alexnodeland/stackr/pull/17))

### Documentation

- **rfc**: RFC-0003 one repository, lattice ([#43](https://github.com/alexnodeland/stackr/pull/43))
- **rfc**: [reflexr#45](https://github.com/alexnodeland/reflexr/issues/45) is implemented, so RFC-0002's phase 1 can start ([#39](https://github.com/alexnodeland/stackr/pull/39))
- **rfc**: Name RFC-0002's bridged events as reflexr ADR-0039 decided ([#35](https://github.com/alexnodeland/stackr/pull/35))
- **rfc**: Link RFC-0002's prerequisites to the issues filed for them ([#34](https://github.com/alexnodeland/stackr/pull/34))
- **rfc**: RFC-0002 the combined system ([#30](https://github.com/alexnodeland/stackr/pull/30))
- Add the documentation site and brand ([#23](https://github.com/alexnodeland/stackr/pull/23))
- **rfc**: Tick RFC-0001 phase 5, the application template ([#18](https://github.com/alexnodeland/stackr/pull/18))
- **adr**: Record ports and adapters for the stack ([#10](https://github.com/alexnodeland/stackr/pull/10))
- Add the stackr design: RFC-0001 and ADRs ([#1](https://github.com/alexnodeland/stackr/pull/1))

### Refactoring

- **scripts**: Keep shellcheck's one exception in .shellcheckrc ([#42](https://github.com/alexnodeland/stackr/pull/42))
- Read settings one way, keep the stack's addresses in one file, and build the docs once ([#38](https://github.com/alexnodeland/stackr/pull/38))

### Testing

- **smoke**: Run an application from the template against the stack ([#16](https://github.com/alexnodeland/stackr/pull/16))

### Miscellaneous

- Lay the foundation for the stack ([#9](https://github.com/alexnodeland/stackr/pull/9))
- Initial commit
