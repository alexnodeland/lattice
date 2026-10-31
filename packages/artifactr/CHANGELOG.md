# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1](https://github.com/alexnodeland/lattice/compare/artifactr-v0.4.0...artifactr-v0.4.1) (2026-10-31)


### Bug Fixes

* **artifactr:** read a mini app's HTML with its own tool, which skips prompt-injection ([#1262](https://github.com/alexnodeland/lattice/issues/1262)) ([91c52ec](https://github.com/alexnodeland/lattice/commit/91c52eccd5417ef5f2f000eedfc196811ad1a93f))

## [0.4.0](https://github.com/alexnodeland/lattice/compare/artifactr-v0.3.0...artifactr-v0.4.0) (2026-10-30)


### Features

* **mcp:** let post_message name the model of the turn it starts ([#1153](https://github.com/alexnodeland/lattice/issues/1153)) ([52ebbd7](https://github.com/alexnodeland/lattice/commit/52ebbd7076f3dfcdf9dedae47798315c09c98fc6)), closes [#824](https://github.com/alexnodeland/lattice/issues/824)


### Bug Fixes

* **files:** install Blender's libraries in Nightly, and keep how a script ended ([#1158](https://github.com/alexnodeland/lattice/issues/1158)) ([5fa9f7d](https://github.com/alexnodeland/lattice/commit/5fa9f7d0cbb45c16ee312ba1d138d21fd413038d)), closes [#783](https://github.com/alexnodeland/lattice/issues/783)
* **stack:** name each pg-up's compose project with a random token ([#1163](https://github.com/alexnodeland/lattice/issues/1163)) ([585b868](https://github.com/alexnodeland/lattice/commit/585b8689a4cdc68475c994b32b9e3bc57a91c64e))

## [0.3.0](https://github.com/alexnodeland/lattice/compare/artifactr-v0.2.1...artifactr-v0.3.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **artifactr:** diagrams' revisions thinned, and workspaces tended every hour ([#730](https://github.com/alexnodeland/lattice/issues/730))
* **artifactr:** a claim is lost only as storage says, so a stalled holder keeps its run and its message ([#692](https://github.com/alexnodeland/lattice/issues/692))
* **artifactr,portalr:** `ask_user` takes `questions` (one to four, each with `question`, `header`, two to four `options` of `label`, `description` and `recommended`, and `multiple` and `other`) in place of `question` and `choices`. An `answer_deferred` to it carries `{"answers": [{"selected": [...], "other": ...}, ...]}`, one per question, or `{"reply": ...}`; a plain string is refused as `validation_failed`. The agent's call returns each question beside its answer. The protocol schema names the shapes `ask_user` and `ask_user_answer`. This is a break in the wire contract, which the griffe-based breaks check (lattice ADR-0012) doesn't cover; it is marked here and in the title.

### Features

* a native file's proposal says what it does, in words and change by change ([#1093](https://github.com/alexnodeland/lattice/issues/1093)) ([ced2769](https://github.com/alexnodeland/lattice/commit/ced27692c5592ac135444bf698505276a39628c6)), closes [#1090](https://github.com/alexnodeland/lattice/issues/1090)
* **artifactr,artifactr-files:** native files as artifacts, phase 1 of RFC-0003 ([#346](https://github.com/alexnodeland/lattice/issues/346)) ([c61165b](https://github.com/alexnodeland/lattice/commit/c61165b36f553eaaec6e3cb53698c1350b20be56))
* **artifactr,grantr:** a message chooses the model of the turn it starts ([#823](https://github.com/alexnodeland/lattice/issues/823)) ([97ab516](https://github.com/alexnodeland/lattice/commit/97ab516bf785c48606073a41790a01870da0f496))
* **artifactr,portalr,stackr:** fail a run that waits on nothing, tell of a message that starts nothing, and carry usage on every end ([#790](https://github.com/alexnodeland/lattice/issues/790)) ([04b8573](https://github.com/alexnodeland/lattice/commit/04b85738f3b43824d957ff83bc1d3d1cf211e067))
* **artifactr,portalr:** a tenant's page waiters bounded, pages asked together rendered once ([#647](https://github.com/alexnodeland/lattice/issues/647)) ([7bf5a96](https://github.com/alexnodeland/lattice/commit/7bf5a966313476b937ec09c676da27a7c956fc84))
* **artifactr,portalr:** ask_user asks questions with options, and the chat shows tool calls, sides, failures and its stream ([#423](https://github.com/alexnodeland/lattice/issues/423)) ([7463e94](https://github.com/alexnodeland/lattice/commit/7463e945526c4ce7156d2b279e2da54b82158824))
* **artifactr,portalr:** connected apps, an operator's own FreeCAD or Blender through a vetted MCP server, code approved on every call ([#450](https://github.com/alexnodeland/lattice/issues/450)) ([5fbb431](https://github.com/alexnodeland/lattice/commit/5fbb431eb763dffa58d946bb25917121fda54067))
* **artifactr,portalr:** exact token counts per model request, live and at a run's end ([#817](https://github.com/alexnodeland/lattice/issues/817)) ([222b34d](https://github.com/alexnodeland/lattice/commit/222b34d2c338876ab0fd8b2dd7a034118873b46d))
* **artifactr,portalr:** revisions that read as what changed, not as escaped JSON ([#431](https://github.com/alexnodeland/lattice/issues/431)) ([a68f2cb](https://github.com/alexnodeland/lattice/commit/a68f2cbe7219bfac7003b303ca55e1a0d0c496f3))
* **artifactr:** connected apps take turns across processes, count a workspace's code calls an hour, refuse oversized images, and keep approvals across a restart ([#572](https://github.com/alexnodeland/lattice/issues/572)) ([fdfff42](https://github.com/alexnodeland/lattice/commit/fdfff4225bf1840b6995b4f0e96d6feab31665d6))
* **artifactr:** diagrams' data: an element-scoped patch, its checks and what the agent reads, with diagrams off by default ([#563](https://github.com/alexnodeland/lattice/issues/563)) ([9f8f2d5](https://github.com/alexnodeland/lattice/commit/9f8f2d571a766e78c8a3e86693732608dbb9a6d8))
* **artifactr:** diagrams' revisions thinned, and workspaces tended every hour ([#730](https://github.com/alexnodeland/lattice/issues/730)) ([fcdefda](https://github.com/alexnodeland/lattice/commit/fcdefdaf158922e780c482f24ee2b4250f7dd657))
* **artifactr:** fold artifactr-files into artifactr as the files extra; lattice ADR-0026 ([#362](https://github.com/alexnodeland/lattice/issues/362)) ([be176b1](https://github.com/alexnodeland/lattice/commit/be176b1283a8bc5f337a9c423641a44c5b94c857))
* **artifactr:** the agent creates a native file of any type the workspace can edit ([#911](https://github.com/alexnodeland/lattice/issues/911)) ([ff57c17](https://github.com/alexnodeland/lattice/commit/ff57c1783dbacf0d028b15aa5cfe841162cff7f0))
* **artifactr:** the agent draws and edits diagrams through a converter, and old tombstones are swept ([#680](https://github.com/alexnodeland/lattice/issues/680)) ([e906df5](https://github.com/alexnodeland/lattice/commit/e906df5f998274c82a26b69cc7adbcca68fa1345))
* **artifactr:** WordCraft 0.11.0's host bridge through the shim, and the pin raised ([#775](https://github.com/alexnodeland/lattice/issues/775)) ([e439d47](https://github.com/alexnodeland/lattice/commit/e439d47e9882ff88c6ce36c7b33032168f6da2a5))
* **diagrams:** a diagram's commits bridged as its elements changed, and comments on them ([#733](https://github.com/alexnodeland/lattice/issues/733)) ([d69702d](https://github.com/alexnodeland/lattice/commit/d69702dd651f43e581439d4329b418d21f43c7ae))
* **diagrams:** edit a diagram on its canvas, and put images on it ([#719](https://github.com/alexnodeland/lattice/issues/719)) ([7adf8f4](https://github.com/alexnodeland/lattice/commit/7adf8f4d88378e4f0b876953b9b9e87b89cc0918))
* **diagrams:** presence on a diagram, and the others' revisions as they arrive ([#726](https://github.com/alexnodeland/lattice/issues/726)) ([e422e1e](https://github.com/alexnodeland/lattice/commit/e422e1e6869fd71beb637c8dce461a83c51e1a0d))
* **files,portalr:** a native file's page: its manifest, who has it, its pages, a download and its words compared ([#390](https://github.com/alexnodeland/lattice/issues/390)) ([2c91e6b](https://github.com/alexnodeland/lattice/commit/2c91e6b673e259d0ea9dcc91af63534b52125afa))
* **files,portalr:** a person's upload over HTTP, told by its bytes, read before it is committed, and held to quotas ([#454](https://github.com/alexnodeland/lattice/issues/454)) ([8a59dd9](https://github.com/alexnodeland/lattice/commit/8a59dd9fe4fe9e8d48065e37d1ebe1766092953c))
* **files,portalr:** uploads shared per tenant, a crafting app's project capped as it streams, and the upload list on the kit's rows ([#525](https://github.com/alexnodeland/lattice/issues/525)) ([804d278](https://github.com/alexnodeland/lattice/commit/804d278fcdf57f577551d58b32a3451af8c6ca6c))
* **files,stackr:** native files in a generated application, each app's worker with no route out and its editor on loopback ([#444](https://github.com/alexnodeland/lattice/issues/444)) ([8b5258a](https://github.com/alexnodeland/lattice/commit/8b5258a78570c6626a652074d56775994e560718))
* **files,stackr:** the generated application's uploads held back as its .env says, a busy refusal costs no pace, each kind's own cap up front ([#539](https://github.com/alexnodeland/lattice/issues/539)) ([d6adaf3](https://github.com/alexnodeland/lattice/commit/d6adaf37f3b801e3cc3ef3106d774c9f195daf87))
* **files:** Blender as native files, on the script dialect, with no file that may run Python ([#445](https://github.com/alexnodeland/lattice/issues/445)) ([6b55967](https://github.com/alexnodeland/lattice/commit/6b5596713c023bf205cefcb4d42cdeede7dec9e4))
* **files:** CADCraft, PhotoCraft, VectorCraft, DesignCraft and FigCraft as native files ([#417](https://github.com/alexnodeland/lattice/issues/417)) ([3c5ad4c](https://github.com/alexnodeland/lattice/commit/3c5ad4cd8ee91a3cd6ab5dcc43c173d0f2614781))
* **files:** check-out and check-in over HTTP, and WordCraft's browser build on its own origin (RFC-0003 phase 4) ([#385](https://github.com/alexnodeland/lattice/issues/385)) ([1f39723](https://github.com/alexnodeland/lattice/commit/1f39723229c4175bfc010500f8a04a9ec97de575))
* **files:** every crafting app declared once, on two dialects' adapters, pinned on its own ([#394](https://github.com/alexnodeland/lattice/issues/394)) ([3d1c635](https://github.com/alexnodeland/lattice/commit/3d1c635b07c7cb2eb4dad039c206a08196bc6760))
* **files:** FilmCraft, EffectCraft and SoundCraft projects as native files, kept only whole, and LightCraft export only ([#447](https://github.com/alexnodeland/lattice/issues/447)) ([0d6d4db](https://github.com/alexnodeland/lattice/commit/0d6d4db26591566314383282e6a163062dd42373))
* **files:** FreeCAD as native files, on a script dialect, with no Python a file or an agent brings ([#428](https://github.com/alexnodeland/lattice/issues/428)) ([2bced02](https://github.com/alexnodeland/lattice/commit/2bced0258e8bc8c9f819445b34ce0b8704163483))
* **files:** GridCraft, DeckCraft and PdfCraft as native files ([#418](https://github.com/alexnodeland/lattice/issues/418)) ([17f6483](https://github.com/alexnodeland/lattice/commit/17f6483db7140ab65c96335f21f708611eecd7cb))
* **files:** the agent's tools for native files, behind each app's switch (RFC-0003 phase 3) ([#378](https://github.com/alexnodeland/lattice/issues/378)) ([d6b353a](https://github.com/alexnodeland/lattice/commit/d6b353aa19ed1493fc7723db3a307b0414248615))
* **files:** the editor's shim, a gate for each app, and an app for each type whose check-ins keep their format ([#401](https://github.com/alexnodeland/lattice/issues/401)) ([0b23e62](https://github.com/alexnodeland/lattice/commit/0b23e624e0a2e8e3e899a926cc41865cf3395b66))
* **files:** the worker that runs an app on hostile files under limits, and the Worker app that calls it ([#415](https://github.com/alexnodeland/lattice/issues/415)) ([7dd08d8](https://github.com/alexnodeland/lattice/commit/7dd08d8b124ab2d615c368e142c894f56857493b))
* **files:** WordCraft headless, pinned by checksum, with a nightly fidelity report (RFC-0003 phase 2) ([#374](https://github.com/alexnodeland/lattice/issues/374)) ([4d67fa7](https://github.com/alexnodeland/lattice/commit/4d67fa7e4fb05c6fe98f03777995661f6a557840))
* **integrations:** one switch per workspace for every integration: lattice-core's port, grantr's store and artifactr's gate ([#369](https://github.com/alexnodeland/lattice/issues/369)) ([bec7dfd](https://github.com/alexnodeland/lattice/commit/bec7dfd99b4d35a74bea8cd757e941b0d9df315b))
* **lattice-core,artifactr:** a connected app's tools narrowed per workspace, and the operator's offer of reads and edits ([#645](https://github.com/alexnodeland/lattice/issues/645)) ([b50d261](https://github.com/alexnodeland/lattice/commit/b50d2617f7a5259d0bedf374b2f942971447d287))
* **lattice-core,grantr,artifactr:** settings each tier may only narrow, stored and audited in grantr, and a connected app's hourly limit read from them ([#609](https://github.com/alexnodeland/lattice/issues/609)) ([8b23639](https://github.com/alexnodeland/lattice/commit/8b236399fdcf3bd7cfb87dd89f3cdaec89e1022c))
* **portalr,artifactr,lattice-core:** several portal origins, with aliases beside each and a union policy ([#792](https://github.com/alexnodeland/lattice/issues/792)) ([87e3949](https://github.com/alexnodeland/lattice/commit/87e3949c7a3d38d3bac2f8c4c2c1087c368fcf6e))
* **portalr,artifactr:** window.host in every mini app, so generated apps get the bridge's shapes and the host's colours right by default ([#434](https://github.com/alexnodeland/lattice/issues/434)) ([00c8cd0](https://github.com/alexnodeland/lattice/commit/00c8cd078b401775e6aed313da9d85ec70268390))
* **portalr,lattice-core,grantr:** a connected app's tools chosen in admin by checkbox, each with its risk, and Settings opened to a workspace's admins ([#661](https://github.com/alexnodeland/lattice/issues/661)) ([1cf8395](https://github.com/alexnodeland/lattice/commit/1cf83959913d9ba7b5681e861a98be76be157fc9))
* **portalr,stackr:** mini apps inline in their thread, with a full view, and the template running them out of the box ([#419](https://github.com/alexnodeland/lattice/issues/419)) ([42dde93](https://github.com/alexnodeland/lattice/commit/42dde93e5a1f32d05996b191c2230cc64d7bb124))
* **portalr:** a diagram's card, its text version, and its canvas to look at ([#699](https://github.com/alexnodeland/lattice/issues/699)) ([ac45691](https://github.com/alexnodeland/lattice/commit/ac45691843d0f1f7ad9fa1eb74063386fd2052f9))
* **portalr:** a file the agent created blank says so until its changes are accepted ([#1066](https://github.com/alexnodeland/lattice/issues/1066)) ([a3aed3a](https://github.com/alexnodeland/lattice/commit/a3aed3adc772d1bb718749e5b49aad209d4cb37a))
* **portalr:** a native file's proposal shows its change, in every craft's words ([#1103](https://github.com/alexnodeland/lattice/issues/1103)) ([cf6406c](https://github.com/alexnodeland/lattice/commit/cf6406ca193a6ddad48906b51de2ee92da445c74)), closes [#1090](https://github.com/alexnodeland/lattice/issues/1090)
* **portalr:** mini apps run in their sandbox, on an origin of their own, through portalr's bridge ([#413](https://github.com/alexnodeland/lattice/issues/413)) ([7c3b344](https://github.com/alexnodeland/lattice/commit/7c3b3447d5768833fec0527c4220b753ae8b2e9a))
* **stackr:** every craft has an editor or says why not; the portal says so ([#1106](https://github.com/alexnodeland/lattice/issues/1106)) ([76dcc4d](https://github.com/alexnodeland/lattice/commit/76dcc4d13a3ec3fd418843e431740677792a28a9)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)
* **ui:** forms and dashboards in the chat, phase 1 of RFC-0005, in artifactr and relayr ([#355](https://github.com/alexnodeland/lattice/issues/355)) ([423f37a](https://github.com/alexnodeland/lattice/commit/423f37a24d2f15a33c23c1586569becb60defd08))
* **ui:** mini apps' tools, create_app and update_app, behind ui:mini-apps, and HTML that loads nothing ([#403](https://github.com/alexnodeland/lattice/issues/403)) ([aff807c](https://github.com/alexnodeland/lattice/commit/aff807c2f73606d75f59d6b95faf947b14d29759))
* which kinds an agent's edits apply to directly in Auto, per workspace ([#1109](https://github.com/alexnodeland/lattice/issues/1109)) ([640b338](https://github.com/alexnodeland/lattice/commit/640b3385022e1edd0ed487cf787e40fe7591e08f)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)


### Bug Fixes

* **artifactr,portalr:** a mini app draws every turn from its state, held turn after turn in the real sandbox ([#429](https://github.com/alexnodeland/lattice/issues/429)) ([182bb59](https://github.com/alexnodeland/lattice/commit/182bb59f6ac72fbcc315e39c86df475582d9276e))
* **artifactr,portalr:** secrets named with more around them, a typed already-exists, a bounded try again, and a server's words shown plainly ([#561](https://github.com/alexnodeland/lattice/issues/561)) ([d0ba030](https://github.com/alexnodeland/lattice/commit/d0ba030d62d861869c37a4463777c93e59d9e4ec))
* **artifactr,portalr:** stop the workspace stream reconnecting in a loop when the server drops it as too slow ([#787](https://github.com/alexnodeland/lattice/issues/787)) ([2dd40fd](https://github.com/alexnodeland/lattice/commit/2dd40fd846dff3db628a366aac0b84e88b3f3422))
* **artifactr:** a claim is lost only as storage says, so a stalled holder keeps its run and its message ([#692](https://github.com/alexnodeland/lattice/issues/692)) ([05b5e43](https://github.com/alexnodeland/lattice/commit/05b5e437edf52d3d84e816cac95017da2545f3f9))
* **artifactr:** a diagram's numbers, quoted words and removed elements, as [#571](https://github.com/alexnodeland/lattice/issues/571) found them ([#630](https://github.com/alexnodeland/lattice/issues/630)) ([dc8edb3](https://github.com/alexnodeland/lattice/commit/dc8edb3a71f986cdf893162aa557c1246065548b))
* **artifactr:** a page takes one of the tenant's readings, is kept, and is paced ([#565](https://github.com/alexnodeland/lattice/issues/565)) ([f873e0a](https://github.com/alexnodeland/lattice/commit/f873e0a3e4272e74f89774ae0c8c0229e2467e73))
* **artifactr:** close what tests/ui/test_agent.py opens, so teardown neither hangs nor leaks ([#850](https://github.com/alexnodeland/lattice/issues/850)) ([ca4d1ca](https://github.com/alexnodeland/lattice/commit/ca4d1ca6c0c467714d1dddcf104e2933fc2ffca9))
* **artifactr:** the acceptance run read waits for the run's run_started, not on a 404 ([#673](https://github.com/alexnodeland/lattice/issues/673)) ([1f7fe80](https://github.com/alexnodeland/lattice/commit/1f7fe8028025412ba0dfcd5a41c5015f9108475f))
* **artifactr:** the connected-app scan bounds nesting itself, so code too deep is a finding in every Python ([#675](https://github.com/alexnodeland/lattice/issues/675)) ([62c8e31](https://github.com/alexnodeland/lattice/commit/62c8e3116457b8b2fc35537c2a58c218555de292))
* **files,portalr:** PDF lengths by reference, and every native file's kind in portalr ([#426](https://github.com/alexnodeland/lattice/issues/426)) ([b6e62dd](https://github.com/alexnodeland/lattice/commit/b6e62dd4aa148fed95110777e1f8a4052cf0b3d5))
* **files:** a connection to the worker for each call, so no idle close cuts one off ([#515](https://github.com/alexnodeland/lattice/issues/515)) ([7f1b807](https://github.com/alexnodeland/lattice/commit/7f1b807f40f6b9dca4eb1dc0313cbfdefb666e49))
* **files:** draw a blank FigCraft page as its background, not refuse it ([#1092](https://github.com/alexnodeland/lattice/issues/1092)) ([4d4c155](https://github.com/alexnodeland/lattice/commit/4d4c155dd73ce6944d806f1c49c372dacc829a63)), closes [#1087](https://github.com/alexnodeland/lattice/issues/1087)
* **files:** draw a blank FreeCAD or Blender file's page instead of refusing it ([#1105](https://github.com/alexnodeland/lattice/issues/1105)) ([5fdb4e4](https://github.com/alexnodeland/lattice/commit/5fdb4e4add1b3bc6b582894f74eb846bd5eeb088)), closes [#1094](https://github.com/alexnodeland/lattice/issues/1094)
* **portalr,artifactr:** the select field's Tab test kept off the hover, a worker deadline read as a bound, and badges counted in the style census ([#566](https://github.com/alexnodeland/lattice/issues/566)) ([4193a2b](https://github.com/alexnodeland/lattice/commit/4193a2b02fc8466ab55dc550fd629de05fd1cb20))

## [0.2.1](https://github.com/alexnodeland/lattice/compare/artifactr-v0.2.0...artifactr-v0.2.1) (2026-10-17)


### Bug Fixes

* **deps:** raise the floors on sibling packages to their released versions ([#333](https://github.com/alexnodeland/lattice/issues/333)) ([54ff956](https://github.com/alexnodeland/lattice/commit/54ff9566b418ab8bcbdb797385c2dc0b6e0a10e5))

## [0.2.0](https://github.com/alexnodeland/lattice/compare/artifactr-v0.1.0...artifactr-v0.2.0) (2026-10-17)


### ⚠ BREAKING CHANGES

* **artifactr:** list a tenant's workspaces, those the caller may open ([#71](https://github.com/alexnodeland/lattice/issues/71))
* **agent:** the storage protocol's `Transaction` has a new required method, `save_cursor(name, seq)`, which a custom storage must implement: it saves a named cursor in the same transaction as the transaction's other writes. SQL storages also need migration 0005, which records the upgrade point for existing threads.

### Features

* acceptance tests, with Bruno and Schemathesis against docplan and oncall ([#68](https://github.com/alexnodeland/lattice/issues/68)) ([64ad30e](https://github.com/alexnodeland/lattice/commit/64ad30ef509cd324dc5593d8b0051d0094d30958))
* **artifactr,reflexr:** LiteLLM requests carry the trace tags Langfuse propagates ([#203](https://github.com/alexnodeland/lattice/issues/203)) ([f8423ca](https://github.com/alexnodeland/lattice/commit/f8423ca118385eb81d7a33b0ea405970c7cb05da))
* **artifactr:** leave restricted threads and artifacts out of every read ([#97](https://github.com/alexnodeland/lattice/issues/97)) ([47131df](https://github.com/alexnodeland/lattice/commit/47131df57905ab11c2397fbeae134a842121ebb9))
* **artifactr:** list a tenant's workspaces, those the caller may open ([#71](https://github.com/alexnodeland/lattice/issues/71)) ([e9de583](https://github.com/alexnodeland/lattice/commit/e9de5834af5db691b72026abdd37361142601092)), closes [#5](https://github.com/alexnodeland/lattice/issues/5)
* **artifactr:** run_started names the messages its turn carries out ([#93](https://github.com/alexnodeland/lattice/issues/93)) ([30023de](https://github.com/alexnodeland/lattice/commit/30023de7bd488dc565f18dad82f1df3e6808f238)), closes [#81](https://github.com/alexnodeland/lattice/issues/81)
* **artifactr:** Runner.ask asks for a thread's next turn ([#92](https://github.com/alexnodeland/lattice/issues/92)) ([efd436a](https://github.com/alexnodeland/lattice/commit/efd436a76fb764cb06bf9ddda248ae6b044b7eb9)), closes [#80](https://github.com/alexnodeland/lattice/issues/80)
* **artifactr:** take what a dead holder was asked, once its claim lapses or a runner starts ([#309](https://github.com/alexnodeland/lattice/issues/309)) ([1b08304](https://github.com/alexnodeland/lattice/commit/1b08304b315d3788a9656c5be80e557c08fe222b))
* **grantr:** SQL storage, the admin API, and telemetry ([#60](https://github.com/alexnodeland/lattice/issues/60)) ([d75c4f7](https://github.com/alexnodeland/lattice/commit/d75c4f796ecb0ea2c87a3084a8e6ed1e1d342f11))
* **lattice-core:** a tenant-workspace tag on every LiteLLM request, so spend reads per tenant's workspace ([#190](https://github.com/alexnodeland/lattice/issues/190)) ([95ffe96](https://github.com/alexnodeland/lattice/commit/95ffe9641ecce3797dcfa6dd2276cdcb08d00920))
* **lattice-core:** one package for what the libraries share, starting with tag_required and the NUL check ([#175](https://github.com/alexnodeland/lattice/issues/175)) ([e3074fc](https://github.com/alexnodeland/lattice/commit/e3074fc6afd9e362f263dc8964fe386e8fa65efa))
* **lattice-core:** the OpenTelemetry setup, Langfuse's span filters, the LiteLLM model and the logging guard ([#187](https://github.com/alexnodeland/lattice/issues/187)) ([508d276](https://github.com/alexnodeland/lattice/commit/508d2761b583837e2aeb99880e930a75ed4c32c3))
* **lattice-core:** the routers' refusal schema, shared by artifactr, reflexr and portalr ([#200](https://github.com/alexnodeland/lattice/issues/200)) ([1b335b1](https://github.com/alexnodeland/lattice/commit/1b335b1320d8d6ec14a185e4911e9c0c94dac221))
* **lattice-core:** the SQL helpers the libraries' storages share, behind a sql extra ([#186](https://github.com/alexnodeland/lattice/issues/186)) ([9b6a571](https://github.com/alexnodeland/lattice/commit/9b6a57144d9efdfd933d66b80a86a87ce7e10a8c))
* **portalr:** admin's shell and Home: its own tenant, every tenant for operators, and a card per read ([#160](https://github.com/alexnodeland/lattice/issues/160)) ([6b2436a](https://github.com/alexnodeland/lattice/commit/6b2436a34cc0ba807e879c261ef7a797ad0f0fb3))
* **reflexr:** row-level security in the SQL adapter, with the scheduler's reads on the owner's engine ([#102](https://github.com/alexnodeland/lattice/issues/102)) ([4cb71dd](https://github.com/alexnodeland/lattice/commit/4cb71dd6565955fce589be41f0e0df030a1bc63f))
* **relayr:** row-level security in the SQL ledger, with the followers' start on the owner's engine ([#106](https://github.com/alexnodeland/lattice/issues/106)) ([437ae71](https://github.com/alexnodeland/lattice/commit/437ae71cd2432e0268a189d04cf466501967e3a1))
* **relayr:** the inbound adapter, with followers, the ledger and the bridged types ([#70](https://github.com/alexnodeland/lattice/issues/70)) ([ce51f03](https://github.com/alexnodeland/lattice/commit/ce51f03ca740b903b50c6996ae86b3ab20893c18))
* **relayr:** traces linked across the bridge, sessions tagged with each other, and counters ([#87](https://github.com/alexnodeland/lattice/issues/87)) ([0a08698](https://github.com/alexnodeland/lattice/commit/0a086984fb73e50486d0f6158285e281976da237))
* row-level security in grantr's and artifactr's SQL adapters ([#100](https://github.com/alexnodeland/lattice/issues/100)) ([bc0ab8e](https://github.com/alexnodeland/lattice/commit/bc0ab8eb7abeba0fd5923eb4afa1d93ddb3cd11a))
* **stackr:** one tenant attribute on every signal, and prom-label-proxy for portalr ([#95](https://github.com/alexnodeland/lattice/issues/95)) ([984e309](https://github.com/alexnodeland/lattice/commit/984e3099a5a56a8bb2f6b56b13230850a53ad821))


### Bug Fixes

* a caller the resolver refuses is answered 403, or 400, on every route and stream ([#75](https://github.com/alexnodeland/lattice/issues/75)) ([1c0c66d](https://github.com/alexnodeland/lattice/commit/1c0c66da0193129611ba79d81ed1d4bd176d623f))
* a NUL character in any string is validation_failed, on every storage ([#84](https://github.com/alexnodeland/lattice/issues/84)) ([218d6a6](https://github.com/alexnodeland/lattice/commit/218d6a6fb36c2b0af4f6295664d74dd0bcfefe2f)), closes [#67](https://github.com/alexnodeland/lattice/issues/67)
* **agent:** take each turn from the log, so a message sent as a run ends is carried out once ([#35](https://github.com/alexnodeland/lattice/issues/35)) ([7f4c2ea](https://github.com/alexnodeland/lattice/commit/7f4c2ea53c2ee9e88bb599f11de14ddaa8363bd1))
* **artifactr,reflexr:** redact an access token from the spans' URLs, and the template from uvicorn's logs ([#163](https://github.com/alexnodeland/lattice/issues/163)) ([398d258](https://github.com/alexnodeland/lattice/commit/398d258c81e610c291e8433349f937bbe006d124))
* **artifactr:** wait for the run before the API collection reads it ([#128](https://github.com/alexnodeland/lattice/issues/128)) ([1b05779](https://github.com/alexnodeland/lattice/commit/1b05779c934ccc171c922e53bae2beae6bbda241))
* the OpenAPI documents describe every refusal, and every tag is required ([#90](https://github.com/alexnodeland/lattice/issues/90)) ([0e09c4b](https://github.com/alexnodeland/lattice/commit/0e09c4bd7a2470b5ff0360a1e29857b5370e8106)), closes [#66](https://github.com/alexnodeland/lattice/issues/66) [#82](https://github.com/alexnodeland/lattice/issues/82)
* the thread claim and owner bugs that TLC and the stateful tests found ([#271](https://github.com/alexnodeland/lattice/issues/271)) ([907cad9](https://github.com/alexnodeland/lattice/commit/907cad95a5ae8e5e2c9c168085168c3137266227))
* what ty's trial found: missing [@override](https://github.com/override), context managers' types, and a callable without a name ([#62](https://github.com/alexnodeland/lattice/issues/62)) ([6bca781](https://github.com/alexnodeland/lattice/commit/6bca78150eed3fc1d9e7822206421c4f6df28313))

## [Before lattice]

### Features

- Notices, messages that don't start or steer a turn ([#75](https://github.com/alexnodeland/artifactr/pull/75))
- **otel**: Telemetry that composes with reflexr's, untraced polling and mirror cursors ([#67](https://github.com/alexnodeland/artifactr/pull/67)) (**breaking**)
- **core**: A message id is used once in a workspace ([#66](https://github.com/alexnodeland/artifactr/pull/66)) (**breaking**)
- Carry the trace context on envelopes, as reflexr does ([#65](https://github.com/alexnodeland/artifactr/pull/65)) (**breaking**)
- **scores**: Build the mirror on evalr's score mapping and ports ([#59](https://github.com/alexnodeland/artifactr/pull/59))
- **mcp**: The reads REST has, and commands carried out once per id on every surface ([#56](https://github.com/alexnodeland/artifactr/pull/56)) (**breaking**)
- The rough edges stackr's template found: model settings, a streaming scripted model, a typed MCP resolver ([#57](https://github.com/alexnodeland/artifactr/pull/57))
- **protocol**: Let a client join at the head of the log, and read its tail ([#58](https://github.com/alexnodeland/artifactr/pull/58))
- **examples**: Docplan closes the evaluation loop with the [evals] extra ([#52](https://github.com/alexnodeland/artifactr/pull/52))
- **evals**: The [evals] extra over evalr ([#39](https://github.com/alexnodeland/artifactr/pull/39))
- **examples**: Docplan observed, rated and routed when configured ([#35](https://github.com/alexnodeland/artifactr/pull/35))
- **litellm**: Route agents through a LiteLLM proxy, with typed guardrail blocks ([#34](https://github.com/alexnodeland/artifactr/pull/34))
- **agent**: Typed run failures, recorded with a reason ([#33](https://github.com/alexnodeland/artifactr/pull/33))
- **deploy**: Grafana dashboards, tested against the metric registry ([#32](https://github.com/alexnodeland/artifactr/pull/32))
- **langfuse**: The Langfuse adapter for traces and feedback scores ([#30](https://github.com/alexnodeland/artifactr/pull/30))
- **scores**: Feedback as scores, a log mirror, and their ports ([#29](https://github.com/alexnodeland/artifactr/pull/29))
- **core**: Typed feedback, evaluator actors and the give_feedback command ([#28](https://github.com/alexnodeland/artifactr/pull/28))
- **otel**: Configure_telemetry, an OpenTelemetry SDK adapter ([#27](https://github.com/alexnodeland/artifactr/pull/27))
- **telemetry**: Trace turns, commits and tool calls, with a metric registry ([#26](https://github.com/alexnodeland/artifactr/pull/26))
- **core**: Record each run attempt's trace id ([#25](https://github.com/alexnodeland/artifactr/pull/25))

### Bug fixes

- **mcp**: Refuse an empty command id, and align with reflexr ([#76](https://github.com/alexnodeland/artifactr/pull/76))
- **agent**: Stop a run whose claim is lost, and drop what it records once abandoned ([#74](https://github.com/alexnodeland/artifactr/pull/74))
- **agent**: Record a run left running as abandoned when its thread is next claimed ([#72](https://github.com/alexnodeland/artifactr/pull/72))
- Cancel-safe storage, and a runner that stops its runs at shutdown ([#69](https://github.com/alexnodeland/artifactr/pull/69)) (**breaking**)
- **mcp**: Leave logging as it was when building the MCP server ([#64](https://github.com/alexnodeland/artifactr/pull/64))
- **mcp**: Ask an authorize hook before a client uses a workspace ([#47](https://github.com/alexnodeland/artifactr/pull/47))
- **sql**: Keep one connection per SQLite engine, so transactions queue in order ([#46](https://github.com/alexnodeland/artifactr/pull/46))
- **deploy**: Dashboards stackr can fetch, with rates that have data ([#44](https://github.com/alexnodeland/artifactr/pull/44))
- **otel**: Instrument httpx2 when httpx is not installed ([#37](https://github.com/alexnodeland/artifactr/pull/37))

### Documentation

- An authorize example that serves both people and MCP clients ([#48](https://github.com/alexnodeland/artifactr/pull/48))
- Regenerate the changelog, and have the site regenerate it on every build ([#45](https://github.com/alexnodeland/artifactr/pull/45))
- Render lists on the site as GitHub does, and check them in the build ([#43](https://github.com/alexnodeland/artifactr/pull/43))
- Wrap up RFC-0002: status, open questions and ADR action items ([#36](https://github.com/alexnodeland/artifactr/pull/36))
- **rfc**: RFC-0002 observability, feedback, evaluation and the LLM gateway ([#21](https://github.com/alexnodeland/artifactr/pull/21))

### Refactoring

- One Runner.execute, reads the workspace owns, scores on evalr, and parity with reflexr ([#70](https://github.com/alexnodeland/artifactr/pull/70)) (**breaking**)

### Testing

- No inline suppressions anywhere, as in reflexr ([#40](https://github.com/alexnodeland/artifactr/pull/40))

### Miscellaneous

- Build the docs once, and deploy them in order ([#71](https://github.com/alexnodeland/artifactr/pull/71))
- Build docplan's image and start it, not only validate Compose ([#55](https://github.com/alexnodeland/artifactr/pull/55))
- Hold the docs script to the library's gates, and mark RFC-0002 Implemented ([#41](https://github.com/alexnodeland/artifactr/pull/41))
- A contributor Compose stack and a Compose-based dev container ([#31](https://github.com/alexnodeland/artifactr/pull/31))

## [0.1.0] - 2026-09-28

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

- Publish the site at artifactr.alexnodeland.com from main ([#19](https://github.com/alexnodeland/artifactr/pull/19))
- Add the documentation site and brand ([#16](https://github.com/alexnodeland/artifactr/pull/16))
- Add architecture, thread protocol and ADRs for the library design

### Miscellaneous

- Distribute as artifactr-ai, imported as artifactr ([#18](https://github.com/alexnodeland/artifactr/pull/18))
- Wrap up v0.1: evergreen status, open questions and changelog ([#17](https://github.com/alexnodeland/artifactr/pull/17))
- **deps**: Update only the lockfile, keeping supported version ranges ([#5](https://github.com/alexnodeland/artifactr/pull/5))
- Lay the foundation for the v0.1 library ([#2](https://github.com/alexnodeland/artifactr/pull/2))

[0.1.0]: https://github.com/alexnodeland/lattice/releases/tag/artifactr-v0.1.0
