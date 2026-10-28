# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-compose-first-with-profiles.md) | Docker Compose first, with profiles | Accepted, amended by [0023](0023-opentofu-for-aws-now.md) |
| [0002](0002-local-supabase-through-its-cli.md) | Local Supabase, through its CLI | Accepted, amended by [0019](0019-access-with-grantr-in-the-template.md) |
| [0003](0003-observability-and-gateway-services.md) | The observability and gateway services | Accepted, amended by [0016](0016-stackr-in-lattice.md) and [0028](0028-local-supabase-on-the-loopback.md) |
| [0004](0004-the-application-template.md) | The application template | Accepted |
| [0005](0005-ports-and-adapters-for-the-stack.md) | Ports and adapters for the stack | Accepted |
| [0006](0006-networks-and-published-ports.md) | Networks and published ports | Accepted, amended by [0044](0044-clickhouse-a-profile-of-its-own-and-portalrs-analytics-users.md) |
| [0007](0007-how-telemetry-reaches-the-backends.md) | How telemetry reaches the backends | Accepted |
| [0008](0008-langfuse-and-its-services.md) | Langfuse and its services | Accepted |
| [0009](0009-local-supabase-as-the-database-adapter.md) | Local Supabase as the database adapter | Accepted, amended by [0016](0016-stackr-in-lattice.md) |
| [0010](0010-the-llm-gateway.md) | The LLM gateway | Accepted, amended by [0047](0047-an-upstream-gateway-for-the-model-groups.md) |
| [0011](0011-the-application-template-in-detail.md) | The application template, in detail | Accepted; partly superseded by [0013](0013-how-the-template-pins-the-libraries.md), [0015](0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md) and [0018](0018-the-template-pins-the-libraries-at-its-own-commit.md), and amended by [0016](0016-stackr-in-lattice.md), [0019](0019-access-with-grantr-in-the-template.md) and portalr's [0086](../../portalr/adr/0086-the-composer-chooses-the-model-of-the-next-turn.md) |
| [0012](0012-documentation-site.md) | The documentation site, and publishing it from main | Accepted, amended by [0014](0014-one-docs-build.md), [0016](0016-stackr-in-lattice.md) and [0017](0017-one-site-for-the-family.md) |
| [0013](0013-how-the-template-pins-the-libraries.md) | How the template pins the libraries | Superseded by [0018](0018-the-template-pins-the-libraries-at-its-own-commit.md) |
| [0014](0014-one-docs-build.md) | One docs build | Accepted, amended by [0017](0017-one-site-for-the-family.md) |
| [0015](0015-telemetry-mirrors-shutdown-and-namespaces-in-the-template.md) | Telemetry, mirrors, shutdown and namespaces in the template | Accepted; how mirrors start amended |
| [0016](0016-stackr-in-lattice.md) | stackr in lattice | Accepted, amended by [0018](0018-the-template-pins-the-libraries-at-its-own-commit.md) |
| [0017](0017-one-site-for-the-family.md) | One site for lattice | Accepted |
| [0018](0018-the-template-pins-the-libraries-at-its-own-commit.md) | The template pins the libraries at its own commit | Accepted |
| [0019](0019-access-with-grantr-in-the-template.md) | Access with grantr in the template | Accepted |
| [0020](0020-one-tenant-attribute-and-prom-label-proxy.md) | One tenant attribute, and prom-label-proxy | Accepted |
| [0021](0021-the-bridge-in-the-template.md) | The bridge in the template | Accepted |
| [0022](0022-row-level-security-in-the-template.md) | Row-level security in the template | Accepted |
| [0023](0023-opentofu-for-aws-now.md) | OpenTofu for AWS, now | Accepted |
| [0024](0024-rules-from-chat-in-the-template.md) | Rules from chat in the template | Accepted |
| [0025](0025-what-the-floci-spike-found.md) | What the Floci spike found | Accepted |
| [0026](0026-the-single-host.md) | The single host | Accepted |
| [0027](0027-the-single-hosts-backups.md) | The single host's backups | Accepted, amended by [0031](0031-clickhouses-admin-apart-from-langfuse.md) |
| [0028](0028-local-supabase-on-the-loopback.md) | Local Supabase on the loopback | Accepted, amended by [0045](0045-local-supabase-only-where-docker-keeps-it-on-the-loopback.md) |
| [0029](0029-the-aws-modules-and-tier-1.md) | The AWS modules, and tier 1 | Accepted, amended by [0034](0034-the-stack-on-aws.md) |
| [0030](0030-the-incident-experiment-and-its-postmortem.md) | The incident experiment, and its postmortem | Accepted |
| [0031](0031-clickhouses-admin-apart-from-langfuse.md) | ClickHouse's admin, apart from Langfuse | Accepted, amended by [0044](0044-clickhouse-a-profile-of-its-own-and-portalrs-analytics-users.md) |
| [0032](0032-the-edge-the-services-and-the-state-host.md) | The edge, the services, and the state host | Accepted, amended by [0034](0034-the-stack-on-aws.md) and [0037](0037-the-state-hosts-clickhouse-backups.md) |
| [0033](0033-the-combined-system-proved-in-ci.md) | The combined system, proved in CI | Accepted |
| [0034](0034-the-stack-on-aws.md) | The stack on AWS | Accepted, amended by [0035](0035-the-thin-images.md) |
| [0035](0035-the-thin-images.md) | The thin images | Accepted |
| [0036](0036-tier-2-against-floci.md) | Tier 2, against Floci | Accepted, amended by [0037](0037-the-state-hosts-clickhouse-backups.md) |
| [0037](0037-the-state-hosts-clickhouse-backups.md) | The state host's ClickHouse backups | Accepted |
| [0038](0038-portalr-in-the-template.md) | portalr in the template | Accepted, amended by [0042](0042-a-generated-application-as-a-local-product.md) |
| [0039](0039-the-task-trackers-recipes-checker-and-question.md) | The task trackers' recipes, their checker, and the template's question | Accepted |
| [0040](0040-forms-and-dashboards-in-the-template.md) | Forms and dashboards in the template | Accepted, amended by [0041](0041-integrations-switched-per-workspace-in-the-template.md) |
| [0041](0041-integrations-switched-per-workspace-in-the-template.md) | Integrations switched per workspace in the template | Accepted |
| [0042](0042-a-generated-application-as-a-local-product.md) | A generated application as a local product: one origin, a first run, and the tailnet | Accepted, amended by portalr [0084](../../portalr/adr/0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md) |
| [0043](0043-native-files-in-the-template.md) | Native files in the template: a worker for each app, with no route out, and its editor on a loopback origin | Accepted, amended by [0046](0046-native-files-a-relay-a-slimmer-worker-blender-and-the-editors-at-the-edge.md) and portalr [0084](../../portalr/adr/0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md) |
| [0044](0044-clickhouse-a-profile-of-its-own-and-portalrs-analytics-users.md) | ClickHouse, a profile of its own, and portalr's analytics users | Accepted, amended by [0048](0048-grafanas-clickhouse-data-source-and-the-adoption-dashboard.md) |
| [0045](0045-local-supabase-only-where-docker-keeps-it-on-the-loopback.md) | Local Supabase only where Docker keeps it on the loopback | Accepted |
| [0046](0046-native-files-a-relay-a-slimmer-worker-blender-and-the-editors-at-the-edge.md) | Native files: a relay, a slimmer worker, Blender, and the editors at the edge | Accepted |
| [0047](0047-an-upstream-gateway-for-the-model-groups.md) | An upstream gateway for the model groups | Accepted, amended by [0054](0054-prompt-cache-breakpoints-at-the-gateway.md) |
| [0048](0048-grafanas-clickhouse-data-source-and-the-adoption-dashboard.md) | Grafana's ClickHouse data source and the adoption dashboard | Accepted, amended by [0051](0051-build-time-fetches-bounded-and-tried-again.md) |
| [0049](0049-the-diagrams-worker-excalidraw-in-headless-chromium-behind-a-relay.md) | The diagrams worker: Excalidraw in headless Chromium, behind a relay | Accepted |
| [0050](0050-umami-a-profile-for-operators-journeys-on-the-postgres-adapter.md) | Umami, a profile for operators' journeys, on the postgres adapter | Accepted |
| [0051](0051-build-time-fetches-bounded-and-tried-again.md) | Build-time fetches, bounded and tried again | Accepted |
| [0052](0052-diagrams-tended-every-hour-sweep-thinning-and-collection.md) | Diagrams tended every hour: the sweep, thinning and collection | Accepted |
| [0053](0053-run-everything-together.md) | Run everything together | Accepted, amended by portalr [0084](../../portalr/adr/0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md) |
| [0054](0054-prompt-cache-breakpoints-at-the-gateway.md) | Prompt-cache breakpoints at the gateway | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
