# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-compose-first-with-profiles.md) | Docker Compose first, with profiles | Accepted |
| [0002](0002-local-supabase-through-its-cli.md) | Local Supabase, through its CLI | Accepted |
| [0003](0003-observability-and-gateway-services.md) | The observability and gateway services | Accepted; amended by [0016](0016-stackr-in-lattice.md) |
| [0004](0004-the-application-template.md) | The application template | Accepted |
| [0005](0005-ports-and-adapters-for-the-stack.md) | Ports and adapters for the stack | Accepted |
| [0006](0006-networks-and-published-ports.md) | Networks and published ports | Accepted |
| [0007](0007-how-telemetry-reaches-the-backends.md) | How telemetry reaches the backends | Accepted |
| [0008](0008-langfuse-and-its-services.md) | Langfuse and its services | Accepted |
| [0009](0009-local-supabase-as-the-database-adapter.md) | Local Supabase as the database adapter | Accepted; amended by [0016](0016-stackr-in-lattice.md) |
| [0010](0010-the-llm-gateway.md) | The LLM gateway | Accepted |
| [0011](0011-the-application-template-in-detail.md) | The application template, in detail | Accepted; partly superseded by [0013](0013-how-the-template-pins-the-libraries.md), [0015](0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md) and [0016](0016-stackr-in-lattice.md) |
| [0012](0012-documentation-site.md) | The documentation site, and publishing it from main | Accepted; amended by [0014](0014-one-docs-build.md) and [0017](0017-one-site-for-the-family.md) |
| [0013](0013-how-the-template-pins-the-libraries.md) | How the template pins the libraries | Accepted |
| [0014](0014-one-docs-build.md) | One docs build | Accepted; amended by [0017](0017-one-site-for-the-family.md) |
| [0015](0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md) | Telemetry, mirrors, shutdown and namespaces in the template | Accepted |
| [0016](0016-stackr-in-lattice.md) | stackr in lattice | Accepted |
| [0017](0017-one-site-for-the-family.md) | One site for the family | Accepted |

To add a record, copy [`template.md`](template.md) to the next number and add a row above.
