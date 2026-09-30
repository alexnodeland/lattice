# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Features

- **template**: Add the Copier application template ([#15](https://github.com/alexnodeland/stackr/pull/15))
- **gateway**: Add the LiteLLM proxy with a team per tenant and guardrails ([#14](https://github.com/alexnodeland/stackr/pull/14))
- **supabase**: Run local Supabase as the default database adapter ([#13](https://github.com/alexnodeland/stackr/pull/13))
- **langfuse**: Add self-hosted Langfuse behind the Collector ([#12](https://github.com/alexnodeland/stackr/pull/12))
- **observability**: Add the Collector, LGTM with Pyroscope, and Grafana ([#11](https://github.com/alexnodeland/stackr/pull/11))

### Bug fixes

- **observability**: Tell Grafana that metrics arrive once a minute ([#19](https://github.com/alexnodeland/stackr/pull/19))
- **template**: Stop the reactor even when it fails as it stops ([#17](https://github.com/alexnodeland/stackr/pull/17))

### Documentation

- **rfc**: Tick RFC-0001 phase 5, the application template ([#18](https://github.com/alexnodeland/stackr/pull/18))
- **adr**: Record ports and adapters for the stack ([#10](https://github.com/alexnodeland/stackr/pull/10))
- Add the stackr design: RFC-0001 and ADRs ([#1](https://github.com/alexnodeland/stackr/pull/1))

### Testing

- **smoke**: Run an application from the template against the stack ([#16](https://github.com/alexnodeland/stackr/pull/16))

### Miscellaneous

- Lay the foundation for the stack ([#9](https://github.com/alexnodeland/stackr/pull/9))
- Initial commit
