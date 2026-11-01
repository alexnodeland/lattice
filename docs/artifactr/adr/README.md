# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-python-library-with-sans-io-core.md) | Python library with a sans-IO core | Accepted |
| [0002](0002-single-write-path.md) | One write path: commands through `Workspace.commit` | Accepted |
| [0003](0003-artifact-types-as-pydantic-subclasses.md) | Artifact types are Pydantic subclasses with library-defined patch kinds | Accepted |
| [0004](0004-optimistic-concurrency-and-revisions.md) | Optimistic concurrency and append-only revisions | Accepted, narrowed by [ADR-0071](0071-a-lease-on-an-artifact.md) |
| [0005](0005-one-event-log-per-workspace.md) | One durable event log per workspace | Accepted, amended by 0021 |
| [0006](0006-agent-integration-as-pydantic-ai-capability.md) | Agent integration as a pydantic-ai capability | Accepted, amended by 0017 |
| [0007](0007-caller-owned-live-output.md) | Live output is owned by the caller, not the log | Accepted |
| [0008](0008-agent-perception-and-steering.md) | Agent perception: change notes, fresh rendering, steering | Accepted; its steering amended by 0055 |
| [0009](0009-write-policies-and-non-blocking-proposals.md) | Write policies and non-blocking proposals | Accepted |
| [0010](0010-pausing-with-deferred-tools.md) | Pausing with pydantic-ai deferred tools | Accepted, and an amendment |
| [0011](0011-workspace-scoped-artifacts-and-tenant-handles.md) | Workspace-scoped artifacts and tenant-scoped handles | Accepted |
| [0012](0012-surfaces-websocket-rest-mcp.md) | Surfaces: WebSocket thread protocol, REST commands, MCP | Superseded by 0048 |
| [0013](0013-library-with-reference-implementation.md) | A library with adapters and a reference implementation | Accepted |
| [0014](0014-trunk-based-development-with-rfcs-and-adrs.md) | Trunk-based development with RFCs, ADRs and evergreen docs | Accepted, amended by 0052 |
| [0015](0015-quality-gates.md) | Quality gates | Accepted, amended by 0052 |
| [0016](0016-mit-license.md) | MIT license | Accepted |
| [0017](0017-application-toolsets-and-capability-events.md) | Application toolsets register on the agent; the capability emits capability events | Accepted |
| [0018](0018-core-host-contract.md) | Core's host contract: needs, commit and record | Accepted |
| [0019](0019-storage-protocol-and-workspace-handles.md) | One storage protocol behind workspace handles | Accepted |
| [0020](0020-running-agents-in-threads.md) | Running agents in threads | Accepted; its messages and thread claims amended by 0055 |
| [0021](0021-sql-storage.md) | SQL storage with one dialect-neutral implementation | Accepted |
| [0022](0022-surfaces-over-one-command-handler.md) | Surfaces over one command handler | Superseded by 0048 |
| [0023](0023-documentation-site.md) | The documentation site | Accepted, amended by 0026, 0050 and 0053 |
| [0024](0024-reference-implementation-as-a-workspace-member.md) | The reference implementation as a workspace member | Accepted, amended by 0052 |
| [0025](0025-distribution-name.md) | Distributed as artifactr-ai, imported as artifactr | Accepted |
| [0026](0026-publishing-the-documentation-site.md) | Publishing the documentation site from main | Accepted, amended by 0050 and 0053 |
| [0027](0027-opentelemetry-observability-with-langfuse.md) | OpenTelemetry-native observability, with Langfuse primary | Accepted |
| [0028](0028-typed-feedback-as-events.md) | Typed feedback as events, mirrored to Langfuse | Accepted |
| [0029](0029-evalr-shared-eval-kit.md) | evalr, a shared eval kit | Accepted |
| [0030](0030-compose-and-dev-containers.md) | Contributor Compose and dev containers here, infrastructure in stackr | Accepted; its dev container superseded by lattice ADR-0009, and its dashboard releases by 0054 |
| [0031](0031-litellm-proxy-first.md) | LiteLLM, proxy first, for routing and guardrails | Accepted |
| [0032](0032-libraries-and-the-stackr-template.md) | Libraries, and stackr as the infrastructure template | Accepted, amended by 0052 and 0054 |
| [0033](0033-trace-links-on-runs-and-revisions.md) | Trace links on runs and revisions | Accepted |
| [0034](0034-ports-and-adapters-for-integrations.md) | Ports and adapters for integrations | Accepted |
| [0035](0035-a-turn-is-its-own-trace.md) | A turn is its own trace | Accepted, amended by 0059 |
| [0036](0036-metric-cardinality-through-sdk-views.md) | Metric cardinality through SDK views | Accepted |
| [0037](0037-feedback-targets-and-evaluators.md) | Feedback targets and evaluators | Accepted |
| [0038](0038-feedback-as-scores.md) | Feedback as scores, through ports | Superseded by 0049 |
| [0039](0039-the-langfuse-adapter.md) | The Langfuse adapter | Accepted; its score adapters superseded by 0049 |
| [0040](0040-joining-stackrs-network.md) | Joining stackr's network when it runs | Accepted; its override superseded by lattice ADR-0009 |
| [0041](0041-dashboards-generated-tested-and-released.md) | Dashboards generated, tested and released | Accepted; its release assets superseded by 0054 |
| [0042](0042-typed-run-failures.md) | Typed run failures | Accepted, amended by [0095](0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md) |
| [0043](0043-the-litellm-adapter.md) | The LiteLLM adapter | Accepted |
| [0044](0044-the-evalr-adapter.md) | The evalr adapter | Accepted; its amendment superseded by 0049, and its pin of evalr by 0052 |
| [0045](0045-a-message-id-is-used-once.md) | A message id is used once in a workspace | Accepted |
| [0046](0046-telemetry-that-composes-across-libraries.md) | Telemetry that composes across libraries, untraced polling and mirror cursors | Accepted |
| [0047](0047-cancel-safe-storage.md) | Cancel-safe storage | Accepted |
| [0048](0048-surfaces-over-the-runner.md) | Surfaces over the runner | Accepted; its recorded message's run amended by 0055, its authorization by 0056 |
| [0049](0049-scores-on-evalr.md) | Scores on evalr | Accepted |
| [0050](0050-one-docs-build.md) | One docs build | Accepted, amended by 0053 |
| [0051](0051-notices.md) | Notices: messages that start no turn | Accepted; its direct messages amended by 0055 |
| [0052](0052-artifactr-in-lattice.md) | artifactr in lattice | Accepted |
| [0053](0053-one-site-for-the-family.md) | One site for lattice | Accepted |
| [0054](0054-dashboards-from-the-checkout.md) | Dashboards from the checkout | Accepted |
| [0055](0055-turns-from-the-log.md) | Turns from the log | Accepted; its batching amended by 0057, its claim by 0069, its hand-over by 0070, and amendments |
| [0056](0056-access-asked-in-every-workspace-method.md) | Access asked in every workspace method | Accepted, amended by 0058 and 0062 |
| [0057](0057-a-turn-acts-for-one-author.md) | A turn acts for one author | Accepted |
| [0058](0058-a-tenants-workspaces-listed-by-what-each-actor-may-open.md) | A tenant's workspaces, listed by what each actor may open | Accepted |
| [0059](0059-a-turn-starts-from-an-empty-context.md) | A turn starts from an empty context | Accepted |
| [0060](0060-the-tenant-on-log-records.md) | The tenant on log records | Accepted |
| [0061](0061-a-nul-character-is-refused-at-the-boundary.md) | A NUL character is refused at the boundary | Accepted |
| [0062](0062-restricted-items-left-out-of-every-read.md) | Restricted items left out of every read | Accepted |
| [0063](0063-the-openapi-documents-describe-refusals.md) | The OpenAPI documents describe refusals | Accepted |
| [0064](0064-asking-for-a-threads-next-turn.md) | Asking for a thread's next turn | Accepted |
| [0065](0065-run-started-names-its-messages.md) | `run_started` names its messages | Accepted |
| [0066](0066-row-level-security-under-the-scoping.md) | Row-level security under the scoping | Accepted |
| [0067](0067-a-failed-turns-series-starts-at-zero.md) | A turn's failed series starts at zero | Accepted |
| [0068](0068-an-access-token-redacted-from-span-urls.md) | An access token redacted from the spans' URLs | Accepted, amended by [lattice ADR-0018](../../adr/0018-lattice-core-what-the-libraries-share.md) |
| [0069](0069-a-claim-fences-the-writes-that-consume.md) | A claim fences the writes that consume | Accepted |
| [0070](0070-a-runner-looks-again-for-what-a-dead-holder-was-asked.md) | A runner looks again for what a dead holder was asked | Accepted |
| [0071](0071-a-lease-on-an-artifact.md) | A lease on an artifact | Accepted |
| [0072](0072-native-files-are-manifests-over-json-patch.md) | Native files are manifests over JSON Patch | Accepted |
| [0073](0073-checks-that-refuse-a-command-before-it-commits.md) | Checks that refuse a command before it commits | Accepted |
| [0074](0074-forms-and-dashboards-in-artifactr-ui-behind-the-forms-extra.md) | Forms and dashboards in `artifactr.ui`, behind the `forms` extra | Accepted |
| [0075](0075-forms-refused-at-the-boundary-through-the-checks.md) | Forms refused at the boundary, through the checks | Accepted |
| [0076](0076-the-form-schema-an-allow-list-compiled-to-pydantic.md) | The form schema, an allow-list compiled to Pydantic | Accepted |
| [0077](0077-formats-and-sizes-checked-by-artifactrs-own-code.md) | Formats and sizes, checked by artifactr's own code | Accepted |
| [0078](0078-the-agents-toolset-for-forms-and-no-apps-yet.md) | The agent's toolset for forms, and no apps yet | Accepted |
| [0079](0079-forms-unverified-items-settled.md) | Forms' unverified items, settled | Accepted |
| [0080](0080-integrations-on-or-off-per-workspace.md) | Integrations on or off per workspace | Accepted |
| [0081](0081-a-gate-before-access-integrations-switched-off-answer-not-enabled.md) | A gate before access: integrations switched off answer NotEnabled | Accepted |
| [0082](0082-mini-apps-the-agents-tools-and-html-that-loads-nothing.md) | Mini apps: the agent's tools, and HTML that loads nothing | Accepted |
| [0083](0083-ask-user-asks-questions-with-options.md) | `ask_user` asks questions with options, and takes answers per question | Accepted |
| [0084](0084-what-a-run-records-of-its-calls-and-who-reads-it.md) | What a run records of its calls and its failure, and who reads it | Accepted |
| [0085](0085-connected-apps-an-operators-own-freecad-or-blender-through-a-vetted-mcp-server.md) | Connected apps: an operator's own FreeCAD or Blender, through a vetted MCP server | Accepted, amended by 0087 and 0089 |
| [0086](0086-diagrams-data-an-element-scoped-patch-and-its-checks.md) | Diagrams' data: an element-scoped patch and its checks | Accepted |
| [0087](0087-a-connected-apps-hourly-limit-read-from-settings.md) | A connected app's hourly limit, read from settings | Accepted |
| [0088](0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md) | Excalidraw's phase 0: what the canvas costs and needs | Accepted |
| [0089](0089-a-connected-apps-tools-narrowed-per-workspace.md) | A connected app's tools, narrowed per workspace | Accepted |
| [0090](0090-diagrams-drawn-by-the-agent-through-a-converter.md) | Diagrams drawn by the agent, through a converter | Accepted |
| [0091](0091-diagrams-tombstones-swept-and-their-revisions-thinned.md) | Diagrams' tombstones swept, and their revisions thinned | Accepted, amended by [0094](0094-diagrams-revisions-thinned-to-one-an-actor-every-ten-minutes.md) |
| [0092](0092-a-diagrams-images-uploaded-by-a-person-and-read-where-it-names-them.md) | A diagram's images, uploaded by a person and read where it names them | Accepted |
| [0093](0093-presence-who-has-an-artifact-open-passed-on-and-never-stored.md) | Presence: who has an artifact open, passed on and never stored | Accepted |
| [0094](0094-diagrams-revisions-thinned-to-one-an-actor-every-ten-minutes.md) | Diagrams' revisions thinned to one an actor every ten minutes | Accepted |
| [0095](0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md) | A run that waits on nothing is failed, and a message that starts nothing is told | Accepted |
| [0096](0096-a-run-counts-each-model-request-exactly-live-and-at-its-end.md) | A run counts each model request exactly, live and at its end | Accepted |
| [0097](0097-a-message-chooses-the-model-of-the-turn-it-starts.md) | A message chooses the model of the turn it starts | Accepted |
| [0098](0098-a-mini-apps-html-read-by-its-own-tool-whose-results-skip-prompt-injection.md) | A mini app's HTML read by its own tool, whose results skip prompt-injection | Accepted |
| [0099](0099-artifactrs-tools-as-capabilities-called-through-the-enforcer-whose-policy-asks-approval.md) | artifactr's tools as capabilities, called through the enforcer, whose policy asks approval | Accepted |
| [0100](0100-artifactrs-commands-every-action-a-command-or-listed-with-its-reason.md) | artifactr's commands: every action a command, or listed with its reason | Accepted |
| [0101](0101-a-run-paused-on-an-enforcers-approval-names-it-and-is-answered-in-its-store.md) | A run paused on an enforcer's approval names it, and is answered in its store | Accepted |
| [0102](0102-an-approval-a-run-asked-is-withdrawn-when-the-run-ends-before-it-pauses-on-it.md) | An approval a run asked is withdrawn when the run ends before it pauses on it | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
