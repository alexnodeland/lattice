# artifactr-files

<p>
  <a href="https://lattice.alexnodeland.com/artifactr-files/"><img alt="Docs" src="https://img.shields.io/badge/docs-lattice.alexnodeland.com%2Fartifactr--files-9E0A5E"></a>
  <a href="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml"><img alt="Nightly" src="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12, 3.13 and 3.14" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-9E0A5E">
  <img alt="Coverage: 100%" src="https://img.shields.io/badge/coverage-100%25-9E0A5E">
  <img alt="Typed: pyright strict" src="https://img.shields.io/badge/typed-pyright%20strict-9E0A5E">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/artifactr-files/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-9E0A5E"></a>
</p>

**artifactr-files** gives [artifactr](https://lattice.alexnodeland.com/artifactr/) artifact types for files in native formats, starting with Word documents. An artifact of such a type is a small manifest that names the file's bytes, by their SHA-256, in a blob store: the file is the source of truth, and nothing parses it into fields. It uses only artifactr's public API, and artifactr imports nothing of it.

> **Status:** phase 1 of [lattice RFC-0003](https://lattice.alexnodeland.com/rfcs/0003-native-files-as-artifacts/), unreleased. The types, the blob store, check-outs and the app port are built, with a fake app; the WordCraft adapter, the sandboxed worker, the agent's tools and portalr's check-out come in later phases. It will be on PyPI as `artifactr-files-ai`, imported as `artifactr_files`.

## What it does

- **A manifest over the bytes.** `WordDocument` names its content, text and review (comments and tracked changes) as blobs, with a fingerprint, an outline and how the content was made. Bytes never enter artifactr's log.
- **Revisions that test their base.** Every revision is ordinary JSON Patch whose first operation tests the content's digest, so accepting a proposal made against an old version fails rather than replacing what came after ([artifactr ADR-0072](https://lattice.alexnodeland.com/artifactr/adr/0072-native-files-are-manifests-over-json-patch/)).
- **One writer at a time.** A person's check-out holds a lease on the artifact for eight hours; an agent's edit holds one for the app's call and the commit, 45 seconds. Someone else is refused with `ArtifactBusy` ([artifactr ADR-0071](https://lattice.alexnodeland.com/artifactr/adr/0071-a-lease-on-an-artifact/)).
- **A blob store of its own**, in memory or in SQL behind the `sql`, `sqlite` and `postgres` extras, keyed by tenant, workspace, artifact and digest, with row-level security on PostgreSQL.

## Documentation

artifactr-files' documentation is its section of lattice's site, at **<https://lattice.alexnodeland.com/artifactr-files/>**, built from [`docs/artifactr-files/`](https://github.com/alexnodeland/lattice/tree/main/docs/artifactr-files).

## Contributing

See [CONTRIBUTING.md](https://github.com/alexnodeland/lattice/blob/main/CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr-files/LICENSE)
