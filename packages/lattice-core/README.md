<p align="center">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/lattice-core/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-9E0A5E"></a>
</p>

**lattice-core** is what lattice's libraries, artifactr, reflexr, grantr and relayr, share and must keep identical. They never import one another; each depends on lattice-core instead, and re-exports what it makes public, so an application imports from the library it uses, never from here.

> **Status:** it holds the libraries' JSON Schema helper, `tag_required`, and their check for text a database can't store, `holds_nul`. Their SQL helpers and their OpenTelemetry setup move here next ([lattice ADR-0018](https://lattice.alexnodeland.com/adr/0018-lattice-core-what-the-libraries-share/)). Its distribution is `lattice-core-ai`, since the name `lattice-core` on PyPI is an unrelated project, and it is imported as `lattice_core`.

Nothing about a library's domain belongs here: only code that is the same in two or more of them, and must stay the same. See [lattice-core's documentation](https://lattice.alexnodeland.com/lattice-core/).
