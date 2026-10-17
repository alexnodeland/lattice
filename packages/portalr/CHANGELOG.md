# Changelog

## [0.1.2](https://github.com/alexnodeland/lattice/compare/portalr-v0.1.1...portalr-v0.1.2) (2026-10-17)


### Bug Fixes

* four CI tickets: the select's Tab test, a warning for a second configure_telemetry, and the image tasks' compose projects ([#345](https://github.com/alexnodeland/lattice/issues/345)) ([09b0389](https://github.com/alexnodeland/lattice/commit/09b0389283d63744e324f66e0454a6e8f029e653)), closes [#193](https://github.com/alexnodeland/lattice/issues/193)

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
