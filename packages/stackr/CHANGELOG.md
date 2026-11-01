# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0](https://github.com/alexnodeland/lattice/compare/stackr-v0.3.0...stackr-v0.4.0) (2026-11-01)


### Features

* **grantr:** store each tenant's bindings beside the operator's, under grantr:manage_bindings (RFC-0011 O13) ([#1315](https://github.com/alexnodeland/lattice/issues/1315)) ([c3cf2d7](https://github.com/alexnodeland/lattice/commit/c3cf2d74eded4b38dc231102901c3f592c812022))

## [0.3.0](https://github.com/alexnodeland/lattice/compare/stackr-v0.2.1...stackr-v0.3.0) (2026-11-01)


### Features

* **grantr:** store approvals per tenant, the first answer winning (RFC-0011 phase 3) ([#1284](https://github.com/alexnodeland/lattice/issues/1284)) ([93bd099](https://github.com/alexnodeland/lattice/commit/93bd099685138c9e07dc3e0fdc99157afe8b697d))

## [0.2.1](https://github.com/alexnodeland/lattice/compare/stackr-v0.2.0...stackr-v0.2.1) (2026-10-30)


### Bug Fixes

* **stackr:** tier 2 checks the listener's rules before its smoke ([#1155](https://github.com/alexnodeland/lattice/issues/1155)) ([c70cc6a](https://github.com/alexnodeland/lattice/commit/c70cc6ae7682127ce0404f19fc4a862d6ffc77ff)), closes [#810](https://github.com/alexnodeland/lattice/issues/810)

## [0.2.0](https://github.com/alexnodeland/lattice/compare/stackr-v0.1.0...stackr-v0.2.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **artifactr:** diagrams' revisions thinned, and workspaces tended every hour ([#730](https://github.com/alexnodeland/lattice/issues/730))
* **artifactr,portalr:** `ask_user` takes `questions` (one to four, each with `question`, `header`, two to four `options` of `label`, `description` and `recommended`, and `multiple` and `other`) in place of `question` and `choices`. An `answer_deferred` to it carries `{"answers": [{"selected": [...], "other": ...}, ...]}`, one per question, or `{"reply": ...}`; a plain string is refused as `validation_failed`. The agent's call returns each question beside its answer. The protocol schema names the shapes `ask_user` and `ask_user_answer`. This is a break in the wire contract, which the griffe-based breaks check (lattice ADR-0012) doesn't cover; it is marked here and in the title.

### Features

* **artifactr,grantr:** a message chooses the model of the turn it starts ([#823](https://github.com/alexnodeland/lattice/issues/823)) ([97ab516](https://github.com/alexnodeland/lattice/commit/97ab516bf785c48606073a41790a01870da0f496))
* **artifactr,portalr,stackr:** fail a run that waits on nothing, tell of a message that starts nothing, and carry usage on every end ([#790](https://github.com/alexnodeland/lattice/issues/790)) ([04b8573](https://github.com/alexnodeland/lattice/commit/04b85738f3b43824d957ff83bc1d3d1cf211e067))
* **artifactr,portalr:** ask_user asks questions with options, and the chat shows tool calls, sides, failures and its stream ([#423](https://github.com/alexnodeland/lattice/issues/423)) ([7463e94](https://github.com/alexnodeland/lattice/commit/7463e945526c4ce7156d2b279e2da54b82158824))
* **artifactr,portalr:** connected apps, an operator's own FreeCAD or Blender through a vetted MCP server, code approved on every call ([#450](https://github.com/alexnodeland/lattice/issues/450)) ([5fbb431](https://github.com/alexnodeland/lattice/commit/5fbb431eb763dffa58d946bb25917121fda54067))
* **artifactr:** diagrams' revisions thinned, and workspaces tended every hour ([#730](https://github.com/alexnodeland/lattice/issues/730)) ([fcdefda](https://github.com/alexnodeland/lattice/commit/fcdefdaf158922e780c482f24ee2b4250f7dd657))
* **artifactr:** WordCraft 0.11.0's host bridge through the shim, and the pin raised ([#775](https://github.com/alexnodeland/lattice/issues/775)) ([e439d47](https://github.com/alexnodeland/lattice/commit/e439d47e9882ff88c6ce36c7b33032168f6da2a5))
* **diagrams:** a diagram's commits bridged as its elements changed, and comments on them ([#733](https://github.com/alexnodeland/lattice/issues/733)) ([d69702d](https://github.com/alexnodeland/lattice/commit/d69702dd651f43e581439d4329b418d21f43c7ae))
* **diagrams:** edit a diagram on its canvas, and put images on it ([#719](https://github.com/alexnodeland/lattice/issues/719)) ([7adf8f4](https://github.com/alexnodeland/lattice/commit/7adf8f4d88378e4f0b876953b9b9e87b89cc0918))
* **files,portalr:** a person's upload over HTTP, told by its bytes, read before it is committed, and held to quotas ([#454](https://github.com/alexnodeland/lattice/issues/454)) ([8a59dd9](https://github.com/alexnodeland/lattice/commit/8a59dd9fe4fe9e8d48065e37d1ebe1766092953c))
* **files,stackr:** native files in a generated application, each app's worker with no route out and its editor on loopback ([#444](https://github.com/alexnodeland/lattice/issues/444)) ([8b5258a](https://github.com/alexnodeland/lattice/commit/8b5258a78570c6626a652074d56775994e560718))
* **files,stackr:** the generated application's uploads held back as its .env says, a busy refusal costs no pace, each kind's own cap up front ([#539](https://github.com/alexnodeland/lattice/issues/539)) ([d6adaf3](https://github.com/alexnodeland/lattice/commit/d6adaf37f3b801e3cc3ef3106d774c9f195daf87))
* **grantr,portalr,stackr:** owe a removal's deletion from grantr's audit log ([#725](https://github.com/alexnodeland/lattice/issues/725)) ([895f879](https://github.com/alexnodeland/lattice/commit/895f879997244bec4bec5196ec710d1e702a5153))
* **grantr,portalr:** a person removed from a tenant has their analytics events there deleted ([#695](https://github.com/alexnodeland/lattice/issues/695)) ([d0eedbf](https://github.com/alexnodeland/lattice/commit/d0eedbf9915c1cdace51ecfd15547fbf69c0c3b3))
* **integrations:** one switch per workspace for every integration: lattice-core's port, grantr's store and artifactr's gate ([#369](https://github.com/alexnodeland/lattice/issues/369)) ([bec7dfd](https://github.com/alexnodeland/lattice/commit/bec7dfd99b4d35a74bea8cd757e941b0d9df315b))
* **lattice-core,grantr,artifactr:** settings each tier may only narrow, stored and audited in grantr, and a connected app's hourly limit read from them ([#609](https://github.com/alexnodeland/lattice/issues/609)) ([8b23639](https://github.com/alexnodeland/lattice/commit/8b236399fdcf3bd7cfb87dd89f3cdaec89e1022c))
* make dev runs stackr's stack and an application with the portal beside it, wired together ([#743](https://github.com/alexnodeland/lattice/issues/743)) ([99127cf](https://github.com/alexnodeland/lattice/commit/99127cff52124059e5848d474076d0d0cdcdb963))
* **portalr,stackr:** analytics' relay, with each person's consent, pace and signed session ([#584](https://github.com/alexnodeland/lattice/issues/584)) ([8b25605](https://github.com/alexnodeland/lattice/commit/8b25605ea0ee309e48c86585531b13add31c0e61))
* **portalr,stackr:** choose the model of the next turn: a closed list narrowed per workspace, its listing, and the composer's picker ([#828](https://github.com/alexnodeland/lattice/issues/828)) ([5eef2fb](https://github.com/alexnodeland/lattice/commit/5eef2fb5fd71b13e10ccdfd0e5f6a79cbbd53885))
* **portalr,stackr:** mini apps inline in their thread, with a full view, and the template running them out of the box ([#419](https://github.com/alexnodeland/lattice/issues/419)) ([42dde93](https://github.com/alexnodeland/lattice/commit/42dde93e5a1f32d05996b191c2230cc64d7bb124))
* **portalr,stackr:** portalr brand init and validate, the template's brand kit, and white-labelling docs ([#529](https://github.com/alexnodeland/lattice/issues/529)) ([14bcb9d](https://github.com/alexnodeland/lattice/commit/14bcb9d9ce6c343a8e4d720efde7c433d8e89fc3))
* **portalr,stackr:** portalr's analytics on ClickHouse's own profile, walled per tenant twice ([#564](https://github.com/alexnodeland/lattice/issues/564)) ([6796d2f](https://github.com/alexnodeland/lattice/commit/6796d2f92fc428d5a3317035db559c24f09a150a))
* **portalr:** a request's analytics session on its trace, and a session's traces ([#682](https://github.com/alexnodeland/lattice/issues/682)) ([25e614e](https://github.com/alexnodeland/lattice/commit/25e614e55a8440a995e8e0b1bce2df0ec817d286))
* **portalr:** a tenant's adoption, read from its product analytics, and admin's page of it ([#674](https://github.com/alexnodeland/lattice/issues/674)) ([d2b120b](https://github.com/alexnodeland/lattice/commit/d2b120bf4f3449f57b06a30040dba70dfb20d5a0))
* **portalr:** connected apps opened from the admin and the palette, beside each portal origin ([#1021](https://github.com/alexnodeland/lattice/issues/1021)) ([a5d2e1d](https://github.com/alexnodeland/lattice/commit/a5d2e1d0babe7b5a9839733e89a74cea0c7afda8))
* **portalr:** session replay, built and off until the privacy review is signed (RFC-0008) ([#718](https://github.com/alexnodeland/lattice/issues/718)) ([8d0c449](https://github.com/alexnodeland/lattice/commit/8d0c449c1af09cb23a8e2d5055f1bfa6493a0ad2))
* **portalr:** the app asks before it counts, and counts pages by their route once it may ([#622](https://github.com/alexnodeland/lattice/issues/622)) ([f1d6bb1](https://github.com/alexnodeland/lattice/commit/f1d6bb17eadb615eb4b4d4c09615d78d782d5bcc))
* **stackr,portalr:** ship Liberation Sans 2.1.5 for Excalidraw's, and read each face's licence upstream ([#727](https://github.com/alexnodeland/lattice/issues/727)) ([d26ffd5](https://github.com/alexnodeland/lattice/commit/d26ffd576854b22811d61b1a1880bd0c04dac49e))
* **stackr,portalr:** Umami for operators' journeys, fed by the relay, on networks of its own ([#700](https://github.com/alexnodeland/lattice/issues/700)) ([24a4165](https://github.com/alexnodeland/lattice/commit/24a4165de2b19bb8b869fd609ff5416adcc22f25))
* **stackr:** add prompt-cache breakpoints at the gateway for Anthropic groups ([#804](https://github.com/alexnodeland/lattice/issues/804)) ([3aac556](https://github.com/alexnodeland/lattice/commit/3aac556774ccd44da27ecc3ebc4c139df49cd2f5))
* **stackr:** every craft has an editor or says why not; the portal says so ([#1106](https://github.com/alexnodeland/lattice/issues/1106)) ([76dcc4d](https://github.com/alexnodeland/lattice/commit/76dcc4d13a3ec3fd418843e431740677792a28a9)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)
* **stackr:** Grafana's ClickHouse data source and the adoption dashboard ([#663](https://github.com/alexnodeland/lattice/issues/663)) ([b437466](https://github.com/alexnodeland/lattice/commit/b4374660845879c6087014884a2aafc18668bc6a))
* **stackr:** native files relay, slimmer worker, Blender worker, and editors at the edge ([#567](https://github.com/alexnodeland/lattice/issues/567)) ([eceeb33](https://github.com/alexnodeland/lattice/commit/eceeb33e97ccc9ff5e39cc275bdbfa3aa5940819))
* **stackr:** Plane's and Vikunja's recipes, make tracker-check, and the template's tracker question (lattice RFC-0004) ([#386](https://github.com/alexnodeland/lattice/issues/386)) ([ab0d1a7](https://github.com/alexnodeland/lattice/commit/ab0d1a7b87da7630c16737c2f3433155acfb5bfa))
* **stackr:** refuse local Supabase where Docker ignores the loopback, and an upstream gateway setting ([#562](https://github.com/alexnodeland/lattice/issues/562)) ([e826a92](https://github.com/alexnodeland/lattice/commit/e826a9298d00910fbd7a31e79d3d9a1b79e13c95))
* **stackr:** scripts/wire-app wires an application's .env to the running stack, and the smoke test uses it ([#741](https://github.com/alexnodeland/lattice/issues/741)) ([e9ca2f9](https://github.com/alexnodeland/lattice/commit/e9ca2f974b176d55291075193669038826094811))
* **stackr:** serve mini apps and editors beside the tailnet name, with PORTAL_EXTRA_URLS ([#800](https://github.com/alexnodeland/lattice/issues/800)) ([1dc8baf](https://github.com/alexnodeland/lattice/commit/1dc8baf035fcc87a7dbc3928a4b0720ec749cebe))
* **stackr:** tell the agent it creates native files, and that its edits wait for review ([#1083](https://github.com/alexnodeland/lattice/issues/1083)) ([660176c](https://github.com/alexnodeland/lattice/commit/660176cb3924c8ead34c8e6f83e279ae05a86098))
* **stackr:** the diagrams worker, Excalidraw in headless Chromium behind a relay ([#690](https://github.com/alexnodeland/lattice/issues/690)) ([4c61853](https://github.com/alexnodeland/lattice/commit/4c6185319e3282a14b3d0112d75cfb9f091f8b29))
* **stackr:** umami-retention deletes Umami's replays older than 30 days (ADR-0077) ([#721](https://github.com/alexnodeland/lattice/issues/721)) ([96e9b29](https://github.com/alexnodeland/lattice/commit/96e9b2906b08c37bb31cc68ac3163b86d7781b6d))
* **stackr:** wire filmcraft, effectcraft and soundcraft beside the other crafts ([#909](https://github.com/alexnodeland/lattice/issues/909)) ([3652b2d](https://github.com/alexnodeland/lattice/commit/3652b2d4b11d3e28d6fe39252a4bb5d69cc5bc36))
* **template:** a generated application as a local product: one origin, a first run, and the tailnet ([#414](https://github.com/alexnodeland/lattice/issues/414)) ([894f2be](https://github.com/alexnodeland/lattice/commit/894f2be28251945e27d0b040f21e47d93f5277f5))
* **ui:** forms and dashboards in the chat, phase 1 of RFC-0005, in artifactr and relayr ([#355](https://github.com/alexnodeland/lattice/issues/355)) ([423f37a](https://github.com/alexnodeland/lattice/commit/423f37a24d2f15a33c23c1586569becb60defd08))
* **ui:** forms and dashboards in the chat, portalr's renderers, phase 1 of RFC-0005 ([#392](https://github.com/alexnodeland/lattice/issues/392)) ([c78e43e](https://github.com/alexnodeland/lattice/commit/c78e43e03be8dc296700e2e30b7569f3a35ba851))
* which kinds an agent's edits apply to directly in Auto, per workspace ([#1109](https://github.com/alexnodeland/lattice/issues/1109)) ([640b338](https://github.com/alexnodeland/lattice/commit/640b3385022e1edd0ed487cf787e40fe7591e08f)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)


### Bug Fixes

* **ci:** four flakes that dequeue pull requests, with the likeliest cause removed in each ([#818](https://github.com/alexnodeland/lattice/issues/818)) ([cb0581d](https://github.com/alexnodeland/lattice/commit/cb0581de7c8c01a5a0592f314fdfb8ce05500631))
* **portalr,stackr:** a brand kit's paths never a folder or hidden, nothing hidden copied into the image, and WebRTC from a mini app's own frames an accepted risk ([#573](https://github.com/alexnodeland/lattice/issues/573)) ([7cc614c](https://github.com/alexnodeland/lattice/commit/7cc614c594866357c0da525dd9a07c84e6389acd))
* **stackr,docs:** let prompt-injection read tool results only ([#827](https://github.com/alexnodeland/lattice/issues/827)) ([ce09b84](https://github.com/alexnodeland/lattice/commit/ce09b84cea1473f2d921463a78d4cbcb76479205))
* **stackr,portalr:** define thumbs in the template; say when a workspace has none ([#788](https://github.com/alexnodeland/lattice/issues/788)) ([b6fd363](https://github.com/alexnodeland/lattice/commit/b6fd363359f750e181c165849caf68dcdeaa7e0f))
* **stackr:** bounded, retried fetches for the Grafana plugin, the stack's pulls and the worker's resolve ([#717](https://github.com/alexnodeland/lattice/issues/717)) ([1ef50a3](https://github.com/alexnodeland/lattice/commit/1ef50a3f796ea154963857d4af3fea7d95389c43))
* **stackr:** check-files' stray-process check tolerates a process that ends as it reads /proc ([#735](https://github.com/alexnodeland/lattice/issues/735)) ([c55560b](https://github.com/alexnodeland/lattice/commit/c55560b59b7e32716db3b674a074e799fef1e718))
* **stackr:** the AWS check tries TFLint's ruleset install three times ([#599](https://github.com/alexnodeland/lattice/issues/599)) ([042aecf](https://github.com/alexnodeland/lattice/commit/042aecf6ee5837718bbc16a9e795d550b471029d))
* **stackr:** the template's portal test closes the sqlite3 connection it reads the owed deletions with ([#766](https://github.com/alexnodeland/lattice/issues/766)) ([fd7a4b7](https://github.com/alexnodeland/lattice/commit/fd7a4b7381ca8be6ac27a3f0826aa07ef1b97ed8))

## 0.1.0 (2026-10-17)


### ⚠ BREAKING CHANGES

* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112))
* **stackr:** access with grantr in the template: tenants from memberships, keys, and every command and read checked ([#69](https://github.com/alexnodeland/lattice/issues/69))
* **stackr:** copier.yml no longer has artifactr_rev and reflexr_rev, and make bump-libraries is gone. An application generated from gh:alexnodeland/stackr first changes `_src_path` in its `.copier-answers.yml` to gh:alexnodeland/lattice, then moves to lattice's sources with copier update.

### Features

* **artifactr:** leave restricted threads and artifacts out of every read ([#97](https://github.com/alexnodeland/lattice/issues/97)) ([47131df](https://github.com/alexnodeland/lattice/commit/47131df57905ab11c2397fbeae134a842121ebb9))
* **grantr:** a stored rule acts as itself, in its own workspace ([#121](https://github.com/alexnodeland/lattice/issues/121)) ([23330f4](https://github.com/alexnodeland/lattice/commit/23330f482830884063cb082f03e63a18c4eaf01b))
* **grantr:** the application installs the rules people accept ([#108](https://github.com/alexnodeland/lattice/issues/108)) ([3353706](https://github.com/alexnodeland/lattice/commit/335370646df4db8b1e668a0213afec7154359d24))
* **grantr:** the application lists tenants and workspaces, and writes for code rules ([#99](https://github.com/alexnodeland/lattice/issues/99)) ([22ee3e0](https://github.com/alexnodeland/lattice/commit/22ee3e04b12a6ee65fba26eb5c68a6d26ef6e7ad))
* **portalr:** acceptance against a two-tenant stack, and the UIs in the wheel ([#98](https://github.com/alexnodeland/lattice/issues/98)) ([82c91a5](https://github.com/alexnodeland/lattice/commit/82c91a553e5e5e3660b71c36273b61f9a6941b1d))
* **portalr:** admin's Tools, links into Langfuse and Grafana, and a record of making them ([#215](https://github.com/alexnodeland/lattice/issues/215)) ([7fb93db](https://github.com/alexnodeland/lattice/commit/7fb93dbee09bed58d72698766bcf0dd4469f5f24))
* **reflexr:** ExternalAgentActor gains on_behalf_of ([#74](https://github.com/alexnodeland/lattice/issues/74)) ([dca9e52](https://github.com/alexnodeland/lattice/commit/dca9e52f226fb1008914d5c9d5d579632512331b))
* **relayr:** a rule changed in reflexr directly is proposed back to its artifact ([#136](https://github.com/alexnodeland/lattice/issues/136)) ([eee4893](https://github.com/alexnodeland/lattice/commit/eee4893c753f62c614f0cc72e4ea588fe296a11a))
* **relayr:** row-level security in the SQL ledger, with the followers' start on the owner's engine ([#106](https://github.com/alexnodeland/lattice/issues/106)) ([437ae71](https://github.com/alexnodeland/lattice/commit/437ae71cd2432e0268a189d04cf466501967e3a1))
* **stackr,portalr:** people by email in the template, scenarios against a generated application, size budgets ([#294](https://github.com/alexnodeland/lattice/issues/294)) ([2a59931](https://github.com/alexnodeland/lattice/commit/2a599312939b1a3b428f5031501f8b241b202d1b))
* **stackr:** a security group per service in the AWS recipe, from its callers ([#161](https://github.com/alexnodeland/lattice/issues/161)) ([a5c12a1](https://github.com/alexnodeland/lattice/commit/a5c12a1117557a6c72a462d0082eb91fdf379df4))
* **stackr:** a single host behind Caddy, with GoTrue alone as the auth profile ([#129](https://github.com/alexnodeland/lattice/issues/129)) ([7760e9f](https://github.com/alexnodeland/lattice/commit/7760e9f09f1f897373f69abe9540cba7ee072e93))
* **stackr:** access with grantr in the template: tenants from memberships, keys, and every command and read checked ([#69](https://github.com/alexnodeland/lattice/issues/69)) ([6167895](https://github.com/alexnodeland/lattice/commit/61678950c2338d59d1afa65b3b15911ada84579f))
* **stackr:** check that GoTrue's image follows the Supabase CLI's ([#207](https://github.com/alexnodeland/lattice/issues/207)) ([1292d34](https://github.com/alexnodeland/lattice/commit/1292d3483d8d0807387140c7c7b0e39670660d56))
* **stackr:** envs/prod and envs/floci, the AWS recipe's roots ([#164](https://github.com/alexnodeland/lattice/issues/164)) ([b5268b8](https://github.com/alexnodeland/lattice/commit/b5268b810102241214c6b6accb89ea971e06964e))
* **stackr:** one tenant attribute on every signal, and prom-label-proxy for portalr ([#95](https://github.com/alexnodeland/lattice/issues/95)) ([984e309](https://github.com/alexnodeland/lattice/commit/984e3099a5a56a8bb2f6b56b13230850a53ad821))
* **stackr:** relayr in the template, with the incident timeline example ([#101](https://github.com/alexnodeland/lattice/issues/101)) ([01bd55b](https://github.com/alexnodeland/lattice/commit/01bd55bce826fb66d422a158c23d06a06398903c))
* **stackr:** row-level security in the template, with make db-roles ([#105](https://github.com/alexnodeland/lattice/issues/105)) ([29fa7af](https://github.com/alexnodeland/lattice/commit/29fa7aff86c2377efb15b5c5033ecc90f0779779))
* **stackr:** rules from chat in the template ([#130](https://github.com/alexnodeland/lattice/issues/130)) ([14c26e7](https://github.com/alexnodeland/lattice/commit/14c26e7cca8cf30653bc10c4ec7d1e0bd9bc7451))
* **stackr:** the AWS recipe's edge, services and state host ([#146](https://github.com/alexnodeland/lattice/issues/146)) ([ffac8ba](https://github.com/alexnodeland/lattice/commit/ffac8baa9778eb5034125eb88cb3bb3812c3485a))
* **stackr:** the AWS recipe's one-off tasks' images, stackr-db-init and stackr-auth-keys ([#174](https://github.com/alexnodeland/lattice/issues/174)) ([5d87d79](https://github.com/alexnodeland/lattice/commit/5d87d79a7338a019bfae763117a37e2dd572792e))
* **stackr:** the AWS recipe's thin images that carry a service's configuration ([#170](https://github.com/alexnodeland/lattice/issues/170)) ([6b00bda](https://github.com/alexnodeland/lattice/commit/6b00bda0f5b7faefcc3079af4e2a6e6c1565ed65))
* **stackr:** the AWS recipe's tools, tier 1, and its network, secrets and data modules ([#139](https://github.com/alexnodeland/lattice/issues/139)) ([5e3b5ac](https://github.com/alexnodeland/lattice/commit/5e3b5ac3105f2af99630482a540c443aa9cd5eb9))
* **stackr:** the AWS state host backs ClickHouse up to S3, and proves it restores ([#209](https://github.com/alexnodeland/lattice/issues/209)) ([9fb0196](https://github.com/alexnodeland/lattice/commit/9fb0196622a7a2e679034039e06faacc3bf3393c))
* **stackr:** the incident experiment, and its postmortem ([#141](https://github.com/alexnodeland/lattice/issues/141)) ([1d8b54a](https://github.com/alexnodeland/lattice/commit/1d8b54af59a8f0c3582d80df91d3d14a1c7b21a0))
* **stackr:** the single host's backups, with pgBackRest and ClickHouse's BACKUP, and the restore drill ([#134](https://github.com/alexnodeland/lattice/issues/134)) ([dbf0dbe](https://github.com/alexnodeland/lattice/commit/dbf0dbe01102c6976be7fff8027710d934a2defb))
* **stackr:** the stack module, which puts the AWS recipe together ([#154](https://github.com/alexnodeland/lattice/issues/154)) ([f0b6b90](https://github.com/alexnodeland/lattice/commit/f0b6b90ed342acf9d74a1312e7f4a3928b2b79e1))
* **stackr:** the template gains portalr, with the UIs and the audit trail ([#224](https://github.com/alexnodeland/lattice/issues/224)) ([a267cf1](https://github.com/alexnodeland/lattice/commit/a267cf160ba7332937492f452cebd4da51477b39))
* **stackr:** the template pins the libraries at its own commit, and CI checks them from the checkout ([#51](https://github.com/alexnodeland/lattice/issues/51)) ([cbc28f6](https://github.com/alexnodeland/lattice/commit/cbc28f661a2bdb233b234ff582f1eb7b76e01913))
* **stackr:** tier 2, the AWS recipe applied against Floci, smoked and destroyed ([#182](https://github.com/alexnodeland/lattice/issues/182)) ([e16c8c5](https://github.com/alexnodeland/lattice/commit/e16c8c56b8d92913a09419789d76bcf70048871d))


### Bug Fixes

* **artifactr,reflexr:** redact an access token from the spans' URLs, and the template from uvicorn's logs ([#163](https://github.com/alexnodeland/lattice/issues/163)) ([398d258](https://github.com/alexnodeland/lattice/commit/398d258c81e610c291e8433349f937bbe006d124))
* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112)) ([77b7ab3](https://github.com/alexnodeland/lattice/commit/77b7ab3ef0e3ddbfe1da8f4fbff22aa03a6ba0b5))
* **stackr:** ClickHouse's admin, apart from Langfuse's user ([#143](https://github.com/alexnodeland/lattice/issues/143)) ([25a0520](https://github.com/alexnodeland/lattice/commit/25a052053af73d6ff465046ddb62065a5fc09e15))
* **stackr:** Langfuse's worker starts after the web server's migrations ([#157](https://github.com/alexnodeland/lattice/issues/157)) ([b47baa5](https://github.com/alexnodeland/lattice/commit/b47baa5fe7dbba9841cd8c16705810365f8bd480))
* **stackr:** Langfuse's worker waits for the web server's migrations on AWS ([#167](https://github.com/alexnodeland/lattice/issues/167)) ([e989865](https://github.com/alexnodeland/lattice/commit/e989865019ce86811dfc2310c3b77f2951d6cf59))
* **stackr:** local Supabase publishes at STACKR_BIND, on the loopback by default ([#135](https://github.com/alexnodeland/lattice/issues/135)) ([68ce5f6](https://github.com/alexnodeland/lattice/commit/68ce5f6d93a98e384a3e05ec9839c9747964873e))
* **stackr:** tier 2 waits for LiteLLM's readiness before its smoke asks it ([#269](https://github.com/alexnodeland/lattice/issues/269)) ([00870cb](https://github.com/alexnodeland/lattice/commit/00870cb456c4189aa1f10d870f53022848d3dc9d))
* **template:** check the generated application with lattice's uv, and only when stackr changes ([#3](https://github.com/alexnodeland/lattice/issues/3)) ([47c577f](https://github.com/alexnodeland/lattice/commit/47c577fecdb3cc1dc8682874e18dd2bab79fb885))

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
