# Changelog

## [0.10.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.9.0...portalr-v0.10.0) (2026-11-01)


### Features

* **client:** CommandName, every command the catalogs declare, generated (RFC-0014) ([#1370](https://github.com/alexnodeland/lattice/issues/1370)) ([d938822](https://github.com/alexnodeland/lattice/commit/d9388221020388ea1d57e5d8b99865bca237a815))
* **client:** every request names its command, and commands.used.json lists what the UIs send (RFC-0014) ([#1374](https://github.com/alexnodeland/lattice/issues/1374)) ([563c539](https://github.com/alexnodeland/lattice/commit/563c53915390d5b61260a7debedd0cd2a71e0f88))
* **core:** parity: every operation names its command, and one test holds the catalogs to grantr (RFC-0014 P13) ([#1366](https://github.com/alexnodeland/lattice/issues/1366)) ([0138269](https://github.com/alexnodeland/lattice/commit/013826911c9cb515ef3c45ad49c0afb396f876de))
* **portalr:** a thread's approval card links its approval's page, which says who may answer it (RFC-0011) ([#1365](https://github.com/alexnodeland/lattice/issues/1365)) ([f90d151](https://github.com/alexnodeland/lattice/commit/f90d1519cfa6f5c8f007a1f4bec105ba716bfb4f))

## [0.9.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.8.0...portalr-v0.9.0) (2026-11-01)


### Features

* **artifactr:** a run paused on an enforcer's approval names it, and is answered in its store (RFC-0011) ([#1334](https://github.com/alexnodeland/lattice/issues/1334)) ([c2d6124](https://github.com/alexnodeland/lattice/commit/c2d61249bfb42738ad30d514757c859f6ab8384f))
* **grantr:** connections: grantr objects, one tenant each, read on every call, revoked at once (RFC-0014 P7) ([#1355](https://github.com/alexnodeland/lattice/issues/1355)) ([4bb7559](https://github.com/alexnodeland/lattice/commit/4bb755918dc242ddc8b560b0229b26a2a6033bb7))
* **portalr:** portalr's commands, its admin's reads and the tenant and member it makes (RFC-0014 phase 1) ([#1342](https://github.com/alexnodeland/lattice/issues/1342)) ([be9e038](https://github.com/alexnodeland/lattice/commit/be9e0388e5f9bb6deb5009df99f5e450812cea5d))

## [0.8.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.7.0...portalr-v0.8.0) (2026-11-01)


### Features

* **portalr:** approvals' list and page in the app, and admin's confirm page for admin_high (RFC-0011, ADR-0038) ([#1316](https://github.com/alexnodeland/lattice/issues/1316)) ([ff04974](https://github.com/alexnodeland/lattice/commit/ff04974aeb951c2664dac27c5c0df3900bf93f2c))

## [0.7.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.6.0...portalr-v0.7.0) (2026-11-01)


### Features

* **grantr:** store each tenant's bindings beside the operator's, under grantr:manage_bindings (RFC-0011 O13) ([#1315](https://github.com/alexnodeland/lattice/issues/1315)) ([c3cf2d7](https://github.com/alexnodeland/lattice/commit/c3cf2d74eded4b38dc231102901c3f592c812022))

## [0.6.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.5.0...portalr-v0.6.0) (2026-11-01)


### Features

* **core,portalr:** an approval's deadline is the workspace's approve-within setting (RFC-0011 phase 3) ([#1303](https://github.com/alexnodeland/lattice/issues/1303)) ([fa19735](https://github.com/alexnodeland/lattice/commit/fa19735166dcd4da2ecfd56b3085b17f42942b0b))
* **grantr:** list, read and answer approvals over the admin API (RFC-0011 phase 3) ([#1304](https://github.com/alexnodeland/lattice/issues/1304)) ([464682f](https://github.com/alexnodeland/lattice/commit/464682fa7cf8cd786b7cfb3e6828f793880e5c76))

## [0.5.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.4.0...portalr-v0.5.0) (2026-11-01)


### Features

* **grantr:** answer the enforcer's Authorize and Audit, each call as the person it is for (RFC-0011 phase 3) ([#1291](https://github.com/alexnodeland/lattice/issues/1291)) ([72a2308](https://github.com/alexnodeland/lattice/commit/72a230810666f52db2c5b78c0fedd7d62fa405c8))

## [0.4.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.3.0...portalr-v0.4.0) (2026-11-01)


### Features

* **core,grantr,portalr:** ask approval by the tiers a union-resolved setting names, and confirm admin_high by its caller (RFC-0011 phase 3) ([#1286](https://github.com/alexnodeland/lattice/issues/1286)) ([6d54b2c](https://github.com/alexnodeland/lattice/commit/6d54b2cb851fcb7e4253d8e371369cbc95462186))

## [0.3.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.2.2...portalr-v0.3.0) (2026-11-01)


### Features

* **grantr:** store approvals per tenant, the first answer winning (RFC-0011 phase 3) ([#1284](https://github.com/alexnodeland/lattice/issues/1284)) ([93bd099](https://github.com/alexnodeland/lattice/commit/93bd099685138c9e07dc3e0fdc99157afe8b697d))

## [0.2.2](https://github.com/alexnodeland/lattice/compare/portalr-v0.2.1...portalr-v0.2.2) (2026-10-30)


### Bug Fixes

* **portalr:** give the size budgets near their ceiling 2 to 3% of headroom ([#1187](https://github.com/alexnodeland/lattice/issues/1187)) ([8c85ec7](https://github.com/alexnodeland/lattice/commit/8c85ec7e9fcbb2b98dc90a63adf46c2824e9f368))

## [0.2.1](https://github.com/alexnodeland/lattice/compare/portalr-v0.2.0...portalr-v0.2.1) (2026-10-30)


### Bug Fixes

* **portalr:** design pass follow-ups from [#779](https://github.com/alexnodeland/lattice/issues/779)'s review ([#1159](https://github.com/alexnodeland/lattice/issues/1159)) ([0837644](https://github.com/alexnodeland/lattice/commit/0837644ebef2817f15e3afd125ea3b29371ae78a)), closes [#780](https://github.com/alexnodeland/lattice/issues/780)
* **portalr:** phone chat space follow-ups from [#1114](https://github.com/alexnodeland/lattice/issues/1114)'s review ([#1154](https://github.com/alexnodeland/lattice/issues/1154)) ([3e5ade7](https://github.com/alexnodeland/lattice/commit/3e5ade78616b8b705dee7d1381c5c351114561bc)), closes [#1132](https://github.com/alexnodeland/lattice/issues/1132)

## [0.2.0](https://github.com/alexnodeland/lattice/compare/portalr-v0.1.1...portalr-v0.2.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **artifactr:** diagrams' revisions thinned, and workspaces tended every hour ([#730](https://github.com/alexnodeland/lattice/issues/730))
* **reflexr:** report a rule's validation errors with a structured loc ([#723](https://github.com/alexnodeland/lattice/issues/723))
* **artifactr,portalr:** `ask_user` takes `questions` (one to four, each with `question`, `header`, two to four `options` of `label`, `description` and `recommended`, and `multiple` and `other`) in place of `question` and `choices`. An `answer_deferred` to it carries `{"answers": [{"selected": [...], "other": ...}, ...]}`, one per question, or `{"reply": ...}`; a plain string is refused as `validation_failed`. The agent's call returns each question beside its answer. The protocol schema names the shapes `ask_user` and `ask_user_answer`. This is a break in the wire contract, which the griffe-based breaks check (lattice ADR-0012) doesn't cover; it is marked here and in the title.

### Features

* a native file's proposal says what it does, in words and change by change ([#1093](https://github.com/alexnodeland/lattice/issues/1093)) ([ced2769](https://github.com/alexnodeland/lattice/commit/ced27692c5592ac135444bf698505276a39628c6)), closes [#1090](https://github.com/alexnodeland/lattice/issues/1090)
* **admin:** Integrations, switched per tenant and workspace, and the app's read of them ([#373](https://github.com/alexnodeland/lattice/issues/373)) ([39fd68c](https://github.com/alexnodeland/lattice/commit/39fd68c2cb0b9ea9e18e5e9ec898883b26819f12))
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
* **diagrams:** edit a diagram on its canvas, and put images on it ([#719](https://github.com/alexnodeland/lattice/issues/719)) ([7adf8f4](https://github.com/alexnodeland/lattice/commit/7adf8f4d88378e4f0b876953b9b9e87b89cc0918))
* **diagrams:** presence on a diagram, and the others' revisions as they arrive ([#726](https://github.com/alexnodeland/lattice/issues/726)) ([e422e1e](https://github.com/alexnodeland/lattice/commit/e422e1e6869fd71beb637c8dce461a83c51e1a0d))
* **files,portalr:** a native file's page: its manifest, who has it, its pages, a download and its words compared ([#390](https://github.com/alexnodeland/lattice/issues/390)) ([2c91e6b](https://github.com/alexnodeland/lattice/commit/2c91e6b673e259d0ea9dcc91af63534b52125afa))
* **files,portalr:** a person's upload over HTTP, told by its bytes, read before it is committed, and held to quotas ([#454](https://github.com/alexnodeland/lattice/issues/454)) ([8a59dd9](https://github.com/alexnodeland/lattice/commit/8a59dd9fe4fe9e8d48065e37d1ebe1766092953c))
* **files,portalr:** uploads shared per tenant, a crafting app's project capped as it streams, and the upload list on the kit's rows ([#525](https://github.com/alexnodeland/lattice/issues/525)) ([804d278](https://github.com/alexnodeland/lattice/commit/804d278fcdf57f577551d58b32a3451af8c6ca6c))
* **files,stackr:** the generated application's uploads held back as its .env says, a busy refusal costs no pace, each kind's own cap up front ([#539](https://github.com/alexnodeland/lattice/issues/539)) ([d6adaf3](https://github.com/alexnodeland/lattice/commit/d6adaf37f3b801e3cc3ef3106d774c9f195daf87))
* **files:** Blender as native files, on the script dialect, with no file that may run Python ([#445](https://github.com/alexnodeland/lattice/issues/445)) ([6b55967](https://github.com/alexnodeland/lattice/commit/6b5596713c023bf205cefcb4d42cdeede7dec9e4))
* **files:** every crafting app declared once, on two dialects' adapters, pinned on its own ([#394](https://github.com/alexnodeland/lattice/issues/394)) ([3d1c635](https://github.com/alexnodeland/lattice/commit/3d1c635b07c7cb2eb4dad039c206a08196bc6760))
* **files:** FilmCraft, EffectCraft and SoundCraft projects as native files, kept only whole, and LightCraft export only ([#447](https://github.com/alexnodeland/lattice/issues/447)) ([0d6d4db](https://github.com/alexnodeland/lattice/commit/0d6d4db26591566314383282e6a163062dd42373))
* **files:** FreeCAD as native files, on a script dialect, with no Python a file or an agent brings ([#428](https://github.com/alexnodeland/lattice/issues/428)) ([2bced02](https://github.com/alexnodeland/lattice/commit/2bced0258e8bc8c9f819445b34ce0b8704163483))
* **files:** the editor's shim, a gate for each app, and an app for each type whose check-ins keep their format ([#401](https://github.com/alexnodeland/lattice/issues/401)) ([0b23e62](https://github.com/alexnodeland/lattice/commit/0b23e624e0a2e8e3e899a926cc41865cf3395b66))
* **grantr,portalr,stackr:** owe a removal's deletion from grantr's audit log ([#725](https://github.com/alexnodeland/lattice/issues/725)) ([895f879](https://github.com/alexnodeland/lattice/commit/895f879997244bec4bec5196ec710d1e702a5153))
* **grantr,portalr:** a person removed from a tenant has their analytics events there deleted ([#695](https://github.com/alexnodeland/lattice/issues/695)) ([d0eedbf](https://github.com/alexnodeland/lattice/commit/d0eedbf9915c1cdace51ecfd15547fbf69c0c3b3))
* **integrations:** one switch per workspace for every integration: lattice-core's port, grantr's store and artifactr's gate ([#369](https://github.com/alexnodeland/lattice/issues/369)) ([bec7dfd](https://github.com/alexnodeland/lattice/commit/bec7dfd99b4d35a74bea8cd757e941b0d9df315b))
* **lattice-core,artifactr:** a connected app's tools narrowed per workspace, and the operator's offer of reads and edits ([#645](https://github.com/alexnodeland/lattice/issues/645)) ([b50d261](https://github.com/alexnodeland/lattice/commit/b50d2617f7a5259d0bedf374b2f942971447d287))
* **lattice-core,grantr,artifactr:** settings each tier may only narrow, stored and audited in grantr, and a connected app's hourly limit read from them ([#609](https://github.com/alexnodeland/lattice/issues/609)) ([8b23639](https://github.com/alexnodeland/lattice/commit/8b236399fdcf3bd7cfb87dd89f3cdaec89e1022c))
* **portalr,artifactr,lattice-core:** several portal origins, with aliases beside each and a union policy ([#792](https://github.com/alexnodeland/lattice/issues/792)) ([87e3949](https://github.com/alexnodeland/lattice/commit/87e3949c7a3d38d3bac2f8c4c2c1087c368fcf6e))
* **portalr,artifactr:** window.host in every mini app, so generated apps get the bridge's shapes and the host's colours right by default ([#434](https://github.com/alexnodeland/lattice/issues/434)) ([00c8cd0](https://github.com/alexnodeland/lattice/commit/00c8cd078b401775e6aed313da9d85ec70268390))
* **portalr,grantr,lattice-core:** admin's Settings page, where a level's limits are lowered at the version read, and a changed registry's clamping flagged ([#625](https://github.com/alexnodeland/lattice/issues/625)) ([759505c](https://github.com/alexnodeland/lattice/commit/759505ca8ff08ade1929a2b165c7d00d054311b9))
* **portalr,lattice-core,grantr:** a connected app's tools chosen in admin by checkbox, each with its risk, and Settings opened to a workspace's admins ([#661](https://github.com/alexnodeland/lattice/issues/661)) ([1cf8395](https://github.com/alexnodeland/lattice/commit/1cf83959913d9ba7b5681e861a98be76be157fc9))
* **portalr,stackr:** analytics' relay, with each person's consent, pace and signed session ([#584](https://github.com/alexnodeland/lattice/issues/584)) ([8b25605](https://github.com/alexnodeland/lattice/commit/8b25605ea0ee309e48c86585531b13add31c0e61))
* **portalr,stackr:** choose the model of the next turn: a closed list narrowed per workspace, its listing, and the composer's picker ([#828](https://github.com/alexnodeland/lattice/issues/828)) ([5eef2fb](https://github.com/alexnodeland/lattice/commit/5eef2fb5fd71b13e10ccdfd0e5f6a79cbbd53885))
* **portalr,stackr:** mini apps inline in their thread, with a full view, and the template running them out of the box ([#419](https://github.com/alexnodeland/lattice/issues/419)) ([42dde93](https://github.com/alexnodeland/lattice/commit/42dde93e5a1f32d05996b191c2230cc64d7bb124))
* **portalr,stackr:** portalr brand init and validate, the template's brand kit, and white-labelling docs ([#529](https://github.com/alexnodeland/lattice/issues/529)) ([14bcb9d](https://github.com/alexnodeland/lattice/commit/14bcb9d9ce6c343a8e4d720efde7c433d8e89fc3))
* **portalr,stackr:** portalr's analytics on ClickHouse's own profile, walled per tenant twice ([#564](https://github.com/alexnodeland/lattice/issues/564)) ([6796d2f](https://github.com/alexnodeland/lattice/commit/6796d2f92fc428d5a3317035db559c24f09a150a))
* **portalr:** a command-first layout: top bar, palette, table, split view ([#849](https://github.com/alexnodeland/lattice/issues/849)) ([79831f9](https://github.com/alexnodeland/lattice/commit/79831f96d519ecfcf04b85252279bef20cc1fb23))
* **portalr:** a design pass for consistency, interaction depth and fidelity ([#779](https://github.com/alexnodeland/lattice/issues/779)) ([419f2d8](https://github.com/alexnodeland/lattice/commit/419f2d8027ab3657dda475a21ba9eb217faace89))
* **portalr:** a diagram's card, its text version, and its canvas to look at ([#699](https://github.com/alexnodeland/lattice/issues/699)) ([ac45691](https://github.com/alexnodeland/lattice/commit/ac45691843d0f1f7ad9fa1eb74063386fd2052f9))
* **portalr:** a file is chosen with the kit's button, not the browser's own control ([#703](https://github.com/alexnodeland/lattice/issues/703)) ([7c8c2b0](https://github.com/alexnodeland/lattice/commit/7c8c2b001f60fa12ef0fd6cf58c02ac66fe2fa9f))
* **portalr:** a file the agent created blank says so until its changes are accepted ([#1066](https://github.com/alexnodeland/lattice/issues/1066)) ([a3aed3a](https://github.com/alexnodeland/lattice/commit/a3aed3adc772d1bb718749e5b49aad209d4cb37a))
* **portalr:** a native file's editor takes a phone's whole window ([#1098](https://github.com/alexnodeland/lattice/issues/1098)) ([398500a](https://github.com/alexnodeland/lattice/commit/398500a1c1cf91ac9fb3241ae229130d20bede86)), closes [#1060](https://github.com/alexnodeland/lattice/issues/1060)
* **portalr:** a native file's proposal shows its change, in every craft's words ([#1103](https://github.com/alexnodeland/lattice/issues/1103)) ([cf6406c](https://github.com/alexnodeland/lattice/commit/cf6406ca193a6ddad48906b51de2ee92da445c74)), closes [#1090](https://github.com/alexnodeland/lattice/issues/1090)
* **portalr:** a native file's proposals, outdated and compared page by page, and the check-out pilot's scenarios ([#402](https://github.com/alexnodeland/lattice/issues/402)) ([ba08a52](https://github.com/alexnodeland/lattice/commit/ba08a52acf8f440f6082cffac57b43765fc959af))
* **portalr:** a new version offered to a tab that outlived its build ([#451](https://github.com/alexnodeland/lattice/issues/451)) ([4ac4fa6](https://github.com/alexnodeland/lattice/commit/4ac4fa6f2501534e0a5f2486cbabb98650f2c99b))
* **portalr:** a phone's composer as a field and one footer, its sheets, and the modes named Auto and Ask ([#868](https://github.com/alexnodeland/lattice/issues/868)) ([ed36b7e](https://github.com/alexnodeland/lattice/commit/ed36b7e923eedfc68a6eb0b64e437aaa4edecfe8))
* **portalr:** a phone's tab bar, its search in the bar's place, and New at the title ([#870](https://github.com/alexnodeland/lattice/issues/870)) ([53a84f2](https://github.com/alexnodeland/lattice/commit/53a84f2e15528c9fd8546a5f9a5f81fd3b88f5fc))
* **portalr:** a request's analytics session on its trace, and a session's traces ([#682](https://github.com/alexnodeland/lattice/issues/682)) ([25e614e](https://github.com/alexnodeland/lattice/commit/25e614e55a8440a995e8e0b1bce2df0ec817d286))
* **portalr:** a tab whose build is gone says so, and a thread's draft survives the reload ([#1099](https://github.com/alexnodeland/lattice/issues/1099)) ([4688a6b](https://github.com/alexnodeland/lattice/commit/4688a6bfc71c609d43c987d53f2f622c309b91e8))
* **portalr:** a tenant's adoption, read from its product analytics, and admin's page of it ([#674](https://github.com/alexnodeland/lattice/issues/674)) ([d2b120b](https://github.com/alexnodeland/lattice/commit/d2b120bf4f3449f57b06a30040dba70dfb20d5a0))
* **portalr:** a turn shows its progress, and a call's arguments formatted ([#791](https://github.com/alexnodeland/lattice/issues/791)) ([9542726](https://github.com/alexnodeland/lattice/commit/9542726eb84939f1994de95829ffc41d5b97d640))
* **portalr:** brand kits loaded per deployment, validated, served under a hash, with the index rewritten ([#519](https://github.com/alexnodeland/lattice/issues/519)) ([910a461](https://github.com/alexnodeland/lattice/commit/910a461d3277c6abacf28228214b9374c8935651))
* **portalr:** check a native file out and in: the editor on its own origin, an upload with its progress, and a retry that is safe ([#398](https://github.com/alexnodeland/lattice/issues/398)) ([95e6076](https://github.com/alexnodeland/lattice/commit/95e6076c2583f15525845feebafb42776cef427d))
* **portalr:** connected apps opened from the admin and the palette, beside each portal origin ([#1021](https://github.com/alexnodeland/lattice/issues/1021)) ([a5d2e1d](https://github.com/alexnodeland/lattice/commit/a5d2e1d0babe7b5a9839733e89a74cea0c7afda8))
* **portalr:** disclosures, a button that says it is open and what it opens ([#530](https://github.com/alexnodeland/lattice/issues/530)) ([05d008d](https://github.com/alexnodeland/lattice/commit/05d008d4342222f3b734c66bbb040d3c6f2eb647))
* **portalr:** empty, error and not-found states on the kit's EmptyState and ErrorState, and an upload's refusal names what is taken ([#551](https://github.com/alexnodeland/lattice/issues/551)) ([e33c880](https://github.com/alexnodeland/lattice/commit/e33c880f16733f6b55f5e61b468f48c572425500))
* **portalr:** every kind inline in its thread, a native file read a page at a time and edited in place ([#435](https://github.com/alexnodeland/lattice/issues/435)) ([d62d7b0](https://github.com/alexnodeland/lattice/commit/d62d7b063372c5bfbba00ad9e0d27fe754caef4d))
* **portalr:** first-party WebAssembly in both UIs' policy, listed by digest ([#382](https://github.com/alexnodeland/lattice/issues/382)) ([97e0462](https://github.com/alexnodeland/lattice/commit/97e0462684f7a4d6592229ca79370fb8541a2ddf))
* **portalr:** fold a turn's tool calls into one quiet, dynamic line that unfolds on tap ([#875](https://github.com/alexnodeland/lattice/issues/875)) ([3bece60](https://github.com/alexnodeland/lattice/commit/3bece6020bb3f6f9131a329073d22c168b2ac8ad))
* **portalr:** headings at the outline's level in the type scale's looks, and badges that say what a thing is ([#526](https://github.com/alexnodeland/lattice/issues/526)) ([6b6c9a9](https://github.com/alexnodeland/lattice/commit/6b6c9a97957825ce052bbf21f89e022b20f9ca5d))
* **portalr:** icon buttons with tooltips, and the inline artifact's header and feedback on them ([#504](https://github.com/alexnodeland/lattice/issues/504)) ([c73b4eb](https://github.com/alexnodeland/lattice/commit/c73b4eb3b951b630482fb650ade7f92a5474ad80))
* **portalr:** link variants, breadcrumbs and the skip link, and every link on its variant ([#466](https://github.com/alexnodeland/lattice/issues/466)) ([145b39a](https://github.com/alexnodeland/lattice/commit/145b39a2e48243d7ac1736eba0e7097a665e6bdf))
* **portalr:** list rows, a name, a quieter line beneath it and an end, and the lists on them ([#488](https://github.com/alexnodeland/lattice/issues/488)) ([bb3da38](https://github.com/alexnodeland/lattice/commit/bb3da38244f14ddfdd62bbe2f0af436c6eba4d17))
* **portalr:** mini apps run in their sandbox, on an origin of their own, through portalr's bridge ([#413](https://github.com/alexnodeland/lattice/issues/413)) ([7c3b344](https://github.com/alexnodeland/lattice/commit/7c3b3447d5768833fec0527c4220b753ae8b2e9a))
* **portalr:** pages that say a tool isn't answering, runs that say when, short trace ids, and integrations in words ([#696](https://github.com/alexnodeland/lattice/issues/696)) ([403d71c](https://github.com/alexnodeland/lattice/commit/403d71c70aaa4babb8a69b7d8e0a7d5c9119d4c3))
* **portalr:** rows that tell themselves apart, and ends against the row's end ([#538](https://github.com/alexnodeland/lattice/issues/538)) ([c9b6166](https://github.com/alexnodeland/lattice/commit/c9b6166cb28f982473f495baf4c16fdaba7f8506))
* **portalr:** say when a mini app stopped after an error, with the real error, and let the owner reload or hand it to the assistant ([#854](https://github.com/alexnodeland/lattice/issues/854)) ([a3c0044](https://github.com/alexnodeland/lattice/commit/a3c00449aae8387a062e448d8852e23b909e1163))
* **portalr:** session replay, built and off until the privacy review is signed (RFC-0008) ([#718](https://github.com/alexnodeland/lattice/issues/718)) ([8d0c449](https://github.com/alexnodeland/lattice/commit/8d0c449c1af09cb23a8e2d5055f1bfa6493a0ad2))
* **portalr:** sheets on a phone, the thumb bar, a phone's tables, and a finger measured in the tests ([#786](https://github.com/alexnodeland/lattice/issues/786)) ([d280a19](https://github.com/alexnodeland/lattice/commit/d280a19edf88a888cf4902b86154e574c75d0ce8))
* **portalr:** show a rule as its pipeline, in threads, proposals and the Rules page ([#864](https://github.com/alexnodeland/lattice/issues/864)) ([e070483](https://github.com/alexnodeland/lattice/commit/e0704837fc7515b56eeda3d3a444a7ed76de6d7d)), closes [#838](https://github.com/alexnodeland/lattice/issues/838)
* **portalr:** the app asks before it counts, and counts pages by their route once it may ([#622](https://github.com/alexnodeland/lattice/issues/622)) ([f1d6bb1](https://github.com/alexnodeland/lattice/commit/f1d6bb17eadb615eb4b4d4c09615d78d782d5bcc))
* **portalr:** the brand kits' foundation: token layers at today's values, structural reduced motion, and guard rails ([#452](https://github.com/alexnodeland/lattice/issues/452)) ([692ef8b](https://github.com/alexnodeland/lattice/commit/692ef8b814c5841dabcfd727cb12ce251971a262))
* **portalr:** the example kits get marks of their own, PNG favicons and licences, and nightshade's dark scheme its own neutrals ([#547](https://github.com/alexnodeland/lattice/issues/547)) ([e74ece2](https://github.com/alexnodeland/lattice/commit/e74ece28ec545524b564a3b6a45831c7febeac5e))
* **portalr:** the frame's edges: a skip link in a room of its own, the kit's selection and scrollbars, a scroll clear of the pinned header ([#550](https://github.com/alexnodeland/lattice/issues/550)) ([9fae380](https://github.com/alexnodeland/lattice/commit/9fae380e6cb9be3d0bfccf44406d5d3c01d9ed70))
* **portalr:** the polish pass, desktop and phone ([#805](https://github.com/alexnodeland/lattice/issues/805)) ([#822](https://github.com/alexnodeland/lattice/issues/822)) ([8f0affe](https://github.com/alexnodeland/lattice/commit/8f0affecb765183d3fa0b92d320a9356ba6b32ce))
* **portalr:** the style census enforces the kit's looks, and the last literals it found are tokens ([#556](https://github.com/alexnodeland/lattice/issues/556)) ([aa4c712](https://github.com/alexnodeland/lattice/commit/aa4c71217d2d4e2665f0cafde4c22071a90a55e5))
* **portalr:** the UIs draw the brand kit's mark and name, and say its words when signing in ([#524](https://github.com/alexnodeland/lattice/issues/524)) ([faa9ee0](https://github.com/alexnodeland/lattice/commit/faa9ee0e91e76c92ff652951de9c5a362a7dbaa2))
* **portalr:** tracker links on runs, and relayr's reads for the portal (lattice RFC-0004, phase 3) ([#391](https://github.com/alexnodeland/lattice/issues/391)) ([d4f3500](https://github.com/alexnodeland/lattice/commit/d4f35002fffc723c4259ddcafd1704df9a886b70))
* **reflexr:** report a rule's validation errors with a structured loc ([#723](https://github.com/alexnodeland/lattice/issues/723)) ([d712c87](https://github.com/alexnodeland/lattice/commit/d712c878dd4dfc4974f0b50a1fe9b59ae531aed6))
* **stackr,portalr:** ship Liberation Sans 2.1.5 for Excalidraw's, and read each face's licence upstream ([#727](https://github.com/alexnodeland/lattice/issues/727)) ([d26ffd5](https://github.com/alexnodeland/lattice/commit/d26ffd576854b22811d61b1a1880bd0c04dac49e))
* **stackr,portalr:** Umami for operators' journeys, fed by the relay, on networks of its own ([#700](https://github.com/alexnodeland/lattice/issues/700)) ([24a4165](https://github.com/alexnodeland/lattice/commit/24a4165de2b19bb8b869fd609ff5416adcc22f25))
* **stackr:** every craft has an editor or says why not; the portal says so ([#1106](https://github.com/alexnodeland/lattice/issues/1106)) ([76dcc4d](https://github.com/alexnodeland/lattice/commit/76dcc4d13a3ec3fd418843e431740677792a28a9)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)
* **stackr:** the diagrams worker, Excalidraw in headless Chromium behind a relay ([#690](https://github.com/alexnodeland/lattice/issues/690)) ([4c61853](https://github.com/alexnodeland/lattice/commit/4c6185319e3282a14b3d0112d75cfb9f091f8b29))
* **ui:** forms and dashboards in the chat, phase 1 of RFC-0005, in artifactr and relayr ([#355](https://github.com/alexnodeland/lattice/issues/355)) ([423f37a](https://github.com/alexnodeland/lattice/commit/423f37a24d2f15a33c23c1586569becb60defd08))
* **ui:** forms and dashboards in the chat, portalr's renderers, phase 1 of RFC-0005 ([#392](https://github.com/alexnodeland/lattice/issues/392)) ([c78e43e](https://github.com/alexnodeland/lattice/commit/c78e43e03be8dc296700e2e30b7569f3a35ba851))
* **ui:** highlighting and math, loaded on demand, each with a size budget of its own ([#367](https://github.com/alexnodeland/lattice/issues/367)) ([274fc12](https://github.com/alexnodeland/lattice/commit/274fc12f37eca93c2c9324746422665c9e6fbd9b))
* **ui:** Markdown's basics: code blocks, callouts, footnotes per message, copying, an add-ons seam, and tests under the policy ([#359](https://github.com/alexnodeland/lattice/issues/359)) ([b323c26](https://github.com/alexnodeland/lattice/commit/b323c26bd0e766b9e7675050b0d58878030243ee))
* **ui:** mini apps' tools, create_app and update_app, behind ui:mini-apps, and HTML that loads nothing ([#403](https://github.com/alexnodeland/lattice/issues/403)) ([aff807c](https://github.com/alexnodeland/lattice/commit/aff807c2f73606d75f59d6b95faf947b14d29759))
* which kinds an agent's edits apply to directly in Auto, per workspace ([#1109](https://github.com/alexnodeland/lattice/issues/1109)) ([640b338](https://github.com/alexnodeland/lattice/commit/640b3385022e1edd0ed487cf787e40fe7591e08f)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)


### Bug Fixes

* **artifactr,portalr:** a mini app draws every turn from its state, held turn after turn in the real sandbox ([#429](https://github.com/alexnodeland/lattice/issues/429)) ([182bb59](https://github.com/alexnodeland/lattice/commit/182bb59f6ac72fbcc315e39c86df475582d9276e))
* **artifactr,portalr:** secrets named with more around them, a typed already-exists, a bounded try again, and a server's words shown plainly ([#561](https://github.com/alexnodeland/lattice/issues/561)) ([d0ba030](https://github.com/alexnodeland/lattice/commit/d0ba030d62d861869c37a4463777c93e59d9e4ec))
* **artifactr,portalr:** stop the workspace stream reconnecting in a loop when the server drops it as too slow ([#787](https://github.com/alexnodeland/lattice/issues/787)) ([2dd40fd](https://github.com/alexnodeland/lattice/commit/2dd40fd846dff3db628a366aac0b84e88b3f3422))
* **artifactr:** a page takes one of the tenant's readings, is kept, and is paced ([#565](https://github.com/alexnodeland/lattice/issues/565)) ([f873e0a](https://github.com/alexnodeland/lattice/commit/f873e0a3e4272e74f89774ae0c8c0229e2467e73))
* **ci:** four flakes that dequeue pull requests, with the likeliest cause removed in each ([#818](https://github.com/alexnodeland/lattice/issues/818)) ([cb0581d](https://github.com/alexnodeland/lattice/commit/cb0581de7c8c01a5a0592f314fdfb8ce05500631))
* **files,portalr:** PDF lengths by reference, and every native file's kind in portalr ([#426](https://github.com/alexnodeland/lattice/issues/426)) ([b6e62dd](https://github.com/alexnodeland/lattice/commit/b6e62dd4aa148fed95110777e1f8a4052cf0b3d5))
* four CI tickets: the select's Tab test, a warning for a second configure_telemetry, and the image tasks' compose projects ([#345](https://github.com/alexnodeland/lattice/issues/345)) ([09b0389](https://github.com/alexnodeland/lattice/commit/09b0389283d63744e324f66e0454a6e8f029e653)), closes [#193](https://github.com/alexnodeland/lattice/issues/193)
* **portalr,artifactr:** the select field's Tab test kept off the hover, a worker deadline read as a bound, and badges counted in the style census ([#566](https://github.com/alexnodeland/lattice/issues/566)) ([4193a2b](https://github.com/alexnodeland/lattice/commit/4193a2b02fc8466ab55dc550fd629de05fd1cb20))
* **portalr,stackr:** a brand kit's paths never a folder or hidden, nothing hidden copied into the image, and WebRTC from a mini app's own frames an accepted risk ([#573](https://github.com/alexnodeland/lattice/issues/573)) ([7cc614c](https://github.com/alexnodeland/lattice/commit/7cc614c594866357c0da525dd9a07c84e6389acd))
* **portalr:** a chart's drawing holds no tab stop, a crumb is never the page shown, and the current area keeps an outline under forced colours ([#628](https://github.com/alexnodeland/lattice/issues/628)) ([687f89d](https://github.com/alexnodeland/lattice/commit/687f89d17803ee0941192cc7b94ffb4327b33e04))
* **portalr:** a header's tooltips never cover the control below, and a file's download is in its header ([#533](https://github.com/alexnodeland/lattice/issues/533)) ([2168f13](https://github.com/alexnodeland/lattice/commit/2168f13d2cc5a80025a3591b667cd65c622d2e33))
* **portalr:** a line of code is highlighted whole however slow tokenizing is ([#480](https://github.com/alexnodeland/lattice/issues/480)) ([8588fbd](https://github.com/alexnodeland/lattice/commit/8588fbd369eca287fbbd2f9919c33cd55374a1bd))
* **portalr:** a mini app is shown whole, measured by the sandbox until it says its own height ([#430](https://github.com/alexnodeland/lattice/issues/430)) ([3450c7c](https://github.com/alexnodeland/lattice/commit/3450c7cc7ce342f8e0050137b37ad9e5fe3e03d5))
* **portalr:** a select's resting pointer takes neither its highlight nor its focus ([#654](https://github.com/alexnodeland/lattice/issues/654)) ([bf67e36](https://github.com/alexnodeland/lattice/commit/bf67e36270491dcae6e24059b165bcfb414466cc))
* **portalr:** a server's words never reach a reader, values not valid say where ([#656](https://github.com/alexnodeland/lattice/issues/656)) ([193403a](https://github.com/alexnodeland/lattice/commit/193403a63fac12d2782ba73da88861beda5e2130))
* **portalr:** an updated app shows as the mini app, at its new version, with its tool-call details beneath ([#853](https://github.com/alexnodeland/lattice/issues/853)) ([11a0fbe](https://github.com/alexnodeland/lattice/commit/11a0fbe5864ad2f20925402d9e6b28af8ca2357a))
* **portalr:** both UIs' policy drops 'wasm-unsafe-eval', which nothing they ship needs ([#629](https://github.com/alexnodeland/lattice/issues/629)) ([3666478](https://github.com/alexnodeland/lattice/commit/3666478f5e266aa8222caf44e32646b580dda7dd))
* **portalr:** give a mini app's sandbox the app on its page's load too, and say when an app never starts ([#814](https://github.com/alexnodeland/lattice/issues/814)) ([96ea957](https://github.com/alexnodeland/lattice/commit/96ea957dc8cccb236d3d6d5ad73272f577adec7f))
* **portalr:** hit-test a row's wrapped name on its first line ([#796](https://github.com/alexnodeland/lattice/issues/796)) ([abc5e4d](https://github.com/alexnodeland/lattice/commit/abc5e4d37852e7f026fa65348320e689125f685e))
* **portalr:** icon buttons' follow-ups, an icon link's own handlers, Escape only where asked, a page glyph, pending thumbs in reach ([#520](https://github.com/alexnodeland/lattice/issues/520)) ([ce52eef](https://github.com/alexnodeland/lattice/commit/ce52eef50fc7a717ce201fb6cb4aa0892f5704ae))
* **portalr:** main's lint clean again ([#465](https://github.com/alexnodeland/lattice/issues/465)) ([4d303b7](https://github.com/alexnodeland/lattice/commit/4d303b741092ab8096b0d58491562019dc76f49d))
* **portalr:** no ring round a heading the app focuses, and a line's markers only where they tell series apart ([#693](https://github.com/alexnodeland/lattice/issues/693)) ([0c575c5](https://github.com/alexnodeland/lattice/commit/0c575c5085ee6d7adca4c07d63ca1a4d97d70426))
* **portalr:** phone chat uses its height; one proposal tray; steady sheets ([#1114](https://github.com/alexnodeland/lattice/issues/1114)) ([15e80fa](https://github.com/alexnodeland/lattice/commit/15e80fa0640902399c375a72f9bde94794eb41cb))
* **portalr:** say what went wrong inside a mini app's frame ([#825](https://github.com/alexnodeland/lattice/issues/825)) ([97feff0](https://github.com/alexnodeland/lattice/commit/97feff091afe254fcc386d2ad7521928ff6e3502))
* **portalr:** size the mini app's frames in pixels, so none depends on percentage resolution ([#834](https://github.com/alexnodeland/lattice/issues/834)) ([200ddc1](https://github.com/alexnodeland/lattice/commit/200ddc1c40703fa8f7595b1bcbc11a36d9d9503d))
* **portalr:** slice A follow-ups: a file's download states, focusing the composer without a jump, and the lists' nits ([#544](https://github.com/alexnodeland/lattice/issues/544)) ([5976fbd](https://github.com/alexnodeland/lattice/commit/5976fbda34447fdfcc1f69c5fa85d0a650bf9393))
* **portalr:** the [#524](https://github.com/alexnodeland/lattice/issues/524) leftovers: sign-in's cut name shown whole on hover, ceilings stated as they are ([#537](https://github.com/alexnodeland/lattice/issues/537)) ([e14d297](https://github.com/alexnodeland/lattice/commit/e14d2977f043fd589c4bb3bc8b3083c698158e49))
* **portalr:** the focus after a navigation, in a full view, a download and a waiting question, and one not-found ([#660](https://github.com/alexnodeland/lattice/issues/660)) ([92462c8](https://github.com/alexnodeland/lattice/commit/92462c80184683acf20c6a8538b3b4bd7363e78b))
* **portalr:** the log list scrolls once for each key, so a key pressed before the last scroll settles stays put ([#491](https://github.com/alexnodeland/lattice/issues/491)) ([1643a9b](https://github.com/alexnodeland/lattice/commit/1643a9b7fa4cb9ede1829938ce12120dc4de5be8))
* **portalr:** the person's own messages sit at the right, the assistant's at the left ([#873](https://github.com/alexnodeland/lattice/issues/873)) ([d0b9d42](https://github.com/alexnodeland/lattice/commit/d0b9d422efb75d32da938ceef36f331f84a13301))
* **portalr:** what the keyboard reaches, and the page's end, stay clear of the pinned composer ([#536](https://github.com/alexnodeland/lattice/issues/536)) ([feb4475](https://github.com/alexnodeland/lattice/commit/feb447526e72fadffe97bcd2d48e7bf709aa7497))
* **stackr,portalr:** define thumbs in the template; say when a workspace has none ([#788](https://github.com/alexnodeland/lattice/issues/788)) ([b6fd363](https://github.com/alexnodeland/lattice/commit/b6fd363359f750e181c165849caf68dcdeaa7e0f))


### Performance Improvements

* **portalr:** a native file's parts load as an add-on of the app's own, out of every route's chunks ([#681](https://github.com/alexnodeland/lattice/issues/681)) ([fd51467](https://github.com/alexnodeland/lattice/commit/fd514670fe3231fae92dbb9cdd74c77eeefae580))
* **portalr:** Streamdown's rehype-raw built as nothing, and the diff library out of the first load ([#662](https://github.com/alexnodeland/lattice/issues/662)) ([83668a3](https://github.com/alexnodeland/lattice/commit/83668a38af150889042ade83256bf52b609a67d1))

## [0.1.1](https://github.com/alexnodeland/lattice/compare/portalr-v0.1.0...portalr-v0.1.1) (2026-10-17)


### Bug Fixes

* **deps:** raise the floors on sibling packages to their released versions ([#333](https://github.com/alexnodeland/lattice/issues/333)) ([54ff956](https://github.com/alexnodeland/lattice/commit/54ff9566b418ab8bcbdb797385c2dc0b6e0a10e5))

## 0.1.0 (2026-10-17)


### ⚠ BREAKING CHANGES

* **reflexr:** `Storage` has a new method, `rule_history`, which a storage implemented outside reflexr must add. Migration 0008 adds a column and a partial index to `reflexr_events`, holding the table while it runs. relayr's `INSTALLS_READ` is removed.
* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112))

### Features

* **artifactr:** run_started names the messages its turn carries out ([#93](https://github.com/alexnodeland/lattice/issues/93)) ([30023de](https://github.com/alexnodeland/lattice/commit/30023de7bd488dc565f18dad82f1df3e6808f238)), closes [#81](https://github.com/alexnodeland/lattice/issues/81)
* **grantr:** a tenant's creation is also an entry in the deployment's audit log ([#216](https://github.com/alexnodeland/lattice/issues/216)) ([188bd33](https://github.com/alexnodeland/lattice/commit/188bd334dcf71bfd5739b5d84ba1b284f9f77437))
* **grantr:** read the audit log from its end, with before_seq and last ([#176](https://github.com/alexnodeland/lattice/issues/176)) ([3350daa](https://github.com/alexnodeland/lattice/commit/3350daa165194dee07e9007880c550829ead9330))
* **grantr:** restrict a thread or artifact, and hide it from who holds nothing on it ([#94](https://github.com/alexnodeland/lattice/issues/94)) ([68f7b1a](https://github.com/alexnodeland/lattice/commit/68f7b1ac798ecc67d361fc78560e368d63c24194))
* **grantr:** the audit log, read by type and by actor ([#152](https://github.com/alexnodeland/lattice/issues/152)) ([20e4451](https://github.com/alexnodeland/lattice/commit/20e44513e8fa47b8d8cc6b2ad4590a8aba07329e))
* **grantr:** the catalog, read: the roles a tenant's admins grant, and what a custom role may hold ([#165](https://github.com/alexnodeland/lattice/issues/165)) ([ba086a6](https://github.com/alexnodeland/lattice/commit/ba086a6cdd7d4ea6313646933d2e9036bd9116a9))
* **lattice-core:** one package for what the libraries share, starting with tag_required and the NUL check ([#175](https://github.com/alexnodeland/lattice/issues/175)) ([e3074fc](https://github.com/alexnodeland/lattice/commit/e3074fc6afd9e362f263dc8964fe386e8fa65efa))
* **lattice-core:** the routers' refusal schema, shared by artifactr, reflexr and portalr ([#200](https://github.com/alexnodeland/lattice/issues/200)) ([1b335b1](https://github.com/alexnodeland/lattice/commit/1b335b1320d8d6ec14a185e4911e9c0c94dac221))
* **portalr:** acceptance against a two-tenant stack, and the UIs in the wheel ([#98](https://github.com/alexnodeland/lattice/issues/98)) ([82c91a5](https://github.com/alexnodeland/lattice/commit/82c91a553e5e5e3660b71c36273b61f9a6941b1d))
* **portalr:** Access's Roles and Grants, on grantr's catalog ([#173](https://github.com/alexnodeland/lattice/issues/173)) ([1036ecb](https://github.com/alexnodeland/lattice/commit/1036ecb8da6295453eb7d9ae9535e84692498055))
* **portalr:** admin's Access: members, groups and keys, each where grantr allows its read ([#168](https://github.com/alexnodeland/lattice/issues/168)) ([af80c5d](https://github.com/alexnodeland/lattice/commit/af80c5d7273d8f094fd3235beb4d7b3fbe48e44f))
* **portalr:** admin's Audit, newest on top, filtered by type and maker ([#177](https://github.com/alexnodeland/lattice/issues/177)) ([d621047](https://github.com/alexnodeland/lattice/commit/d6210473f1a29c975281507a0023ce889b6e57de))
* **portalr:** admin's Feedback, summed by day, with the first charts ([#181](https://github.com/alexnodeland/lattice/issues/181)) ([4c5f80b](https://github.com/alexnodeland/lattice/commit/4c5f80b3226a6ae9651cdcedb0170e23f1707e3f))
* **portalr:** admin's Logs without their lines, and a Health section ([#208](https://github.com/alexnodeland/lattice/issues/208)) ([d487bf5](https://github.com/alexnodeland/lattice/commit/d487bf5218b8517ab4f5bf2a8995a49e845b743e))
* **portalr:** admin's Runs, with Retry, Skip and Cancel ([#210](https://github.com/alexnodeland/lattice/issues/210)) ([90897b6](https://github.com/alexnodeland/lattice/commit/90897b6f3e9f1ba0dd0ddc5292b78493be845d80))
* **portalr:** admin's shell and Home: its own tenant, every tenant for operators, and a card per read ([#160](https://github.com/alexnodeland/lattice/issues/160)) ([6b2436a](https://github.com/alexnodeland/lattice/commit/6b2436a34cc0ba807e879c261ef7a797ad0f0fb3))
* **portalr:** admin's Tenants, created with their owner by email, and the deployment's audit log ([#212](https://github.com/alexnodeland/lattice/issues/212)) ([883cc3e](https://github.com/alexnodeland/lattice/commit/883cc3edff67d7f1ff837624dd521f5c1f38e321))
* **portalr:** admin's Tools, links into Langfuse and Grafana, and a record of making them ([#215](https://github.com/alexnodeland/lattice/issues/215)) ([7fb93db](https://github.com/alexnodeland/lattice/commit/7fb93dbee09bed58d72698766bcf0dd4469f5f24))
* **portalr:** admin's Traces, and a trace view written for ui ([#204](https://github.com/alexnodeland/lattice/issues/204)) ([4f8988e](https://github.com/alexnodeland/lattice/commit/4f8988eddb225c2edbdf566647abec543cec6bd1))
* **portalr:** admin's Usage: spend per day, each day against its share of the budget, and each workspace's part ([#188](https://github.com/alexnodeland/lattice/issues/188)) ([6fcfba7](https://github.com/alexnodeland/lattice/commit/6fcfba7e610fabc938fb8357aeae45ae3f6afe77))
* **portalr:** colour-blind mode as a setting in the account menu, kept per browser ([#292](https://github.com/alexnodeland/lattice/issues/292)) ([3e9efd8](https://github.com/alexnodeland/lattice/commit/3e9efd80814f48de58af5a1b97fe71bf56ed9837))
* **portalr:** one chart theme, violet-led series, and a hook for colour-blind mode ([#221](https://github.com/alexnodeland/lattice/issues/221)) ([4bd62f1](https://github.com/alexnodeland/lattice/commit/4bd62f12e1e420b818b39db7fb8010d4db63ea01))
* **portalr:** people shown by email, not by their Supabase id ([#225](https://github.com/alexnodeland/lattice/issues/225)) ([5587b4a](https://github.com/alexnodeland/lattice/commit/5587b4aef72bb66337ec6b0e6f5f918e831f8511))
* **portalr:** portalr's and grantr's marks, and ui's tokens and first primitives ([#64](https://github.com/alexnodeland/lattice/issues/64)) ([cbbeb93](https://github.com/alexnodeland/lattice/commit/cbbeb93f5d39e85e7380c8ed8895f256ca8493bd))
* **portalr:** restricting and sharing a thread, from its menu ([#145](https://github.com/alexnodeland/lattice/issues/145)) ([18db54e](https://github.com/alexnodeland/lattice/commit/18db54e175c4acb22a044e098212de6f722534f0))
* **portalr:** the app's shell: signing in, and the tenant and workspace pickers ([#111](https://github.com/alexnodeland/lattice/issues/111)) ([1927b94](https://github.com/alexnodeland/lattice/commit/1927b94e68fc97d44bb565036a32f94bab722cde))
* **portalr:** the app's Threads area: a workspace's threads, and a chat in each ([#120](https://github.com/alexnodeland/lattice/issues/120)) ([d00552c](https://github.com/alexnodeland/lattice/commit/d00552ca8efae3f8b8e076c8ac89f4bed94117e9))
* **portalr:** the areas on the frame, a danger colour, budget badges, and admin's frame ([#148](https://github.com/alexnodeland/lattice/issues/148)) ([d1d2c79](https://github.com/alexnodeland/lattice/commit/d1d2c798ce9825200106365735efe7083600fddf))
* **portalr:** the Artifacts and Proposals areas: renderers by kind, and diffs by revision ([#123](https://github.com/alexnodeland/lattice/issues/123)) ([99871b1](https://github.com/alexnodeland/lattice/commit/99871b16a80ba77819e0443e6c86ca55d043fdbd))
* **portalr:** the chat's store and components, and Markdown through Streamdown ([#118](https://github.com/alexnodeland/lattice/issues/118)) ([549bfa7](https://github.com/alexnodeland/lattice/commit/549bfa7c648aefcc89fe9314dc7dcffed2ec46f4))
* **portalr:** the client: generated types, the REST clients and queries, and resumable stream stores ([#79](https://github.com/alexnodeland/lattice/issues/79)) ([9747465](https://github.com/alexnodeland/lattice/commit/9747465ce31fa9191f1fdad43df381e1d738adc9))
* **portalr:** the kit's look: a frame, its parts, four tokens and the family's typefaces ([#131](https://github.com/alexnodeland/lattice/issues/131)) ([ad6f74b](https://github.com/alexnodeland/lattice/commit/ad6f74b7fa185298571a6fda0f39fcf280a658c1))
* **portalr:** the router and its readers ([#88](https://github.com/alexnodeland/lattice/issues/88)) ([5548521](https://github.com/alexnodeland/lattice/commit/55485211c1e63677dd8cbb131dbee8d6d15ba465))
* **portalr:** the Rules area: stored rules installed, edited and archived as reflexr's JSON ([#142](https://github.com/alexnodeland/lattice/issues/142)) ([1431ab1](https://github.com/alexnodeland/lattice/commit/1431ab184d28094e350d9ff1873c9adaa8979cb3))
* **portalr:** the Runs area, and thumbs with a comment on runs, turns and artifacts ([#125](https://github.com/alexnodeland/lattice/issues/125)) ([6e8d729](https://github.com/alexnodeland/lattice/commit/6e8d729d9f773e2bcf23a81496f6fdb06992e37c))
* **portalr:** the UI polish pass: charts and a colour-blind hook, form controls, elevation, status colours, alerts and density ([#236](https://github.com/alexnodeland/lattice/issues/236)) ([633dd88](https://github.com/alexnodeland/lattice/commit/633dd8872c6e679de7f7078a5a7bb814510fad98))
* **portalr:** third-party notices for the JavaScript the UIs bundle ([#211](https://github.com/alexnodeland/lattice/issues/211)) ([2939b6b](https://github.com/alexnodeland/lattice/commit/2939b6b8f5dcd2322394acb9e278af1c6e6f86eb))
* **reflexr:** a stored rule's history, read by its name, so relayr finds its installs however far back ([#151](https://github.com/alexnodeland/lattice/issues/151)) ([66e096a](https://github.com/alexnodeland/lattice/commit/66e096aff95e3eabe25a5c02603fb0c7cff8616c))
* **reflexr:** the protocol schema names reflexr's own events, and portalr types them ([#162](https://github.com/alexnodeland/lattice/issues/162)) ([db8bd5e](https://github.com/alexnodeland/lattice/commit/db8bd5e8814ab38c33872e52c1ff2047479c323a))
* **stackr,portalr:** people by email in the template, scenarios against a generated application, size budgets ([#294](https://github.com/alexnodeland/lattice/issues/294)) ([2a59931](https://github.com/alexnodeland/lattice/commit/2a599312939b1a3b428f5031501f8b241b202d1b))
* **stackr:** the AWS recipe's thin images that carry a service's configuration ([#170](https://github.com/alexnodeland/lattice/issues/170)) ([6b00bda](https://github.com/alexnodeland/lattice/commit/6b00bda0f5b7faefcc3079af4e2a6e6c1565ed65))


### Bug Fixes

* **ci:** run the browser projects' tests apart from other tests' containers ([#256](https://github.com/alexnodeland/lattice/issues/256)) ([cc26598](https://github.com/alexnodeland/lattice/commit/cc26598cf2a9e67768b24404f053701c2fec2cda))
* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112)) ([77b7ab3](https://github.com/alexnodeland/lattice/commit/77b7ab3ef0e3ddbfe1da8f4fbff22aa03a6ba0b5))
* **portalr:** each BDD run starts a compose project of its own ([#223](https://github.com/alexnodeland/lattice/issues/223)) ([14fd85c](https://github.com/alexnodeland/lattice/commit/14fd85c128b2e600a8d2de3291931c37f78a44ce))
* **portalr:** UI polish from the screenshots: one width rule, artifact titles, workspace cards, a violet focus ring ([#199](https://github.com/alexnodeland/lattice/issues/199)) ([b8d477a](https://github.com/alexnodeland/lattice/commit/b8d477ac66ef547f7955907bf81eeffdab9ab8e9))
* **portalr:** Vitest's browser servers on 127.0.0.1, so a Chromium reaches its own ([#171](https://github.com/alexnodeland/lattice/issues/171)) ([601db82](https://github.com/alexnodeland/lattice/commit/601db8283a66d6fa9ef100b2797c556b75c45145))
* **portalr:** what admin's screenshots showed: headed places, a named grantee, readable refusals ([#183](https://github.com/alexnodeland/lattice/issues/183)) ([03f10bd](https://github.com/alexnodeland/lattice/commit/03f10bd4e54efd94419550774d6cc3aa2efd0c85))
* **reflexr:** an epoch fences each attempt, so a cancelled and retried one cannot record ([#247](https://github.com/alexnodeland/lattice/issues/247)) ([bc2adfe](https://github.com/alexnodeland/lattice/commit/bc2adfe496dbba06fb483c71fee57f1457e40354))
* the OpenAPI documents describe every refusal, and every tag is required ([#90](https://github.com/alexnodeland/lattice/issues/90)) ([0e09c4b](https://github.com/alexnodeland/lattice/commit/0e09c4bd7a2470b5ff0360a1e29857b5370e8106)), closes [#66](https://github.com/alexnodeland/lattice/issues/66) [#82](https://github.com/alexnodeland/lattice/issues/82)

## Changelog
