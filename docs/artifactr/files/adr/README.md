# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. The proposal behind these is [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md); the decisions it changed in artifactr are [artifactr ADR-0071](../../adr/0071-a-lease-on-an-artifact.md) and [ADR-0072](../../adr/0072-native-files-are-manifests-over-json-patch.md).

ADR-0001 to ADR-0003 record RFC-0003's D5, D2 and D3, ADR-0004 the app port it designs, ADR-0005 its phase 2, WordCraft headless, and ADR-0006 the agent's tools of its phase 3.

This is the native files' own series, inside artifactr's section since `artifactr-files` became artifactr's `files` extra ([lattice ADR-0026](../../../adr/0026-a-distribution-needs-a-reason-integrations-are-extras.md)). Its records keep their numbers, and outside the series one is named "native files ADR-0002"; artifactr's own series is [`docs/artifactr/adr/`](../../adr/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-a-separate-distribution.md) | A separate distribution | Superseded by [lattice ADR-0026](../../../adr/0026-a-distribution-needs-a-reason-integrations-are-extras.md) |
| [0002](0002-blobs-in-a-port-of-the-package.md) | Blobs in a port of the package | Accepted |
| [0003](0003-check-outs-and-agents-edits-under-one-lease.md) | Check-outs and agents' edits under one lease | Accepted |
| [0004](0004-an-app-is-a-port-of-stateless-calls.md) | An app is a port of stateless calls | Accepted; amended by [0005](0005-wordcraft-headless-pinned-by-checksum.md) |
| [0005](0005-wordcraft-headless-pinned-by-checksum.md) | WordCraft headless, pinned by checksum, and what each app declares | Accepted |
| [0006](0006-the-agents-tools-behind-each-apps-switch.md) | The agent's tools, behind each app's switch | Accepted |

To add a record, copy lattice's [ADR template](../../../adr/template.md) to the next number and add a row above.
