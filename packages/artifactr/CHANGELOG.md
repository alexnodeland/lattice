# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Features

- **examples**: Keep docplan's workspaces in a database when configured ([#15](https://github.com/alexnodeland/artifactr/pull/15))
- **sql**: Add SQLAlchemy storage and migrations ([#9](https://github.com/alexnodeland/artifactr/pull/9))
- **examples**: Add docplan, the reference implementation ([#14](https://github.com/alexnodeland/artifactr/pull/14))
- **core**: Describe a proposed edit when it is proposed ([#13](https://github.com/alexnodeland/artifactr/pull/13))
- **core**: Include an artifact's kind when a version is serialized ([#10](https://github.com/alexnodeland/artifactr/pull/10))
- **surfaces**: Add the WebSocket, REST and MCP surfaces ([#8](https://github.com/alexnodeland/artifactr/pull/8))
- **agent**: Add the pydantic-ai capability, live output and runner ([#7](https://github.com/alexnodeland/artifactr/pull/7))
- **workspace**: Add scoped workspace handles over pluggable storage ([#6](https://github.com/alexnodeland/artifactr/pull/6))
- **core**: Add the pure rules, conformance suite and host contract ([#4](https://github.com/alexnodeland/artifactr/pull/4))

### Bug fixes

- **fastapi**: Watch only live runs in the threads a client follows ([#12](https://github.com/alexnodeland/artifactr/pull/12))
- **agent**: Record the result of a tool that retries or fails on its own ([#11](https://github.com/alexnodeland/artifactr/pull/11))

### Documentation

- Add the documentation site and brand ([#16](https://github.com/alexnodeland/artifactr/pull/16))
- Add architecture, thread protocol and ADRs for the library design

### Miscellaneous

- **deps**: Update only the lockfile, keeping supported version ranges ([#5](https://github.com/alexnodeland/artifactr/pull/5))
- Lay the foundation for the v0.1 library ([#2](https://github.com/alexnodeland/artifactr/pull/2))
