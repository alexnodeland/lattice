# Changelog

## [0.2.0](https://github.com/alexnodeland/lattice/compare/grantr-v0.1.0...grantr-v0.2.0) (2026-10-29)


### Features

* **artifactr,grantr:** a message chooses the model of the turn it starts ([#823](https://github.com/alexnodeland/lattice/issues/823)) ([97ab516](https://github.com/alexnodeland/lattice/commit/97ab516bf785c48606073a41790a01870da0f496))
* **artifactr:** diagrams' data: an element-scoped patch, its checks and what the agent reads, with diagrams off by default ([#563](https://github.com/alexnodeland/lattice/issues/563)) ([9f8f2d5](https://github.com/alexnodeland/lattice/commit/9f8f2d571a766e78c8a3e86693732608dbb9a6d8))
* **files,portalr:** a person's upload over HTTP, told by its bytes, read before it is committed, and held to quotas ([#454](https://github.com/alexnodeland/lattice/issues/454)) ([8a59dd9](https://github.com/alexnodeland/lattice/commit/8a59dd9fe4fe9e8d48065e37d1ebe1766092953c))
* **files:** every crafting app declared once, on two dialects' adapters, pinned on its own ([#394](https://github.com/alexnodeland/lattice/issues/394)) ([3d1c635](https://github.com/alexnodeland/lattice/commit/3d1c635b07c7cb2eb4dad039c206a08196bc6760))
* **grantr,portalr,stackr:** owe a removal's deletion from grantr's audit log ([#725](https://github.com/alexnodeland/lattice/issues/725)) ([895f879](https://github.com/alexnodeland/lattice/commit/895f879997244bec4bec5196ec710d1e702a5153))
* **grantr,portalr:** a person removed from a tenant has their analytics events there deleted ([#695](https://github.com/alexnodeland/lattice/issues/695)) ([d0eedbf](https://github.com/alexnodeland/lattice/commit/d0eedbf9915c1cdace51ecfd15547fbf69c0c3b3))
* **integrations:** one switch per workspace for every integration: lattice-core's port, grantr's store and artifactr's gate ([#369](https://github.com/alexnodeland/lattice/issues/369)) ([bec7dfd](https://github.com/alexnodeland/lattice/commit/bec7dfd99b4d35a74bea8cd757e941b0d9df315b))
* **lattice-core,artifactr:** a connected app's tools narrowed per workspace, and the operator's offer of reads and edits ([#645](https://github.com/alexnodeland/lattice/issues/645)) ([b50d261](https://github.com/alexnodeland/lattice/commit/b50d2617f7a5259d0bedf374b2f942971447d287))
* **lattice-core,grantr,artifactr:** settings each tier may only narrow, stored and audited in grantr, and a connected app's hourly limit read from them ([#609](https://github.com/alexnodeland/lattice/issues/609)) ([8b23639](https://github.com/alexnodeland/lattice/commit/8b236399fdcf3bd7cfb87dd89f3cdaec89e1022c))
* **portalr,grantr,lattice-core:** admin's Settings page, where a level's limits are lowered at the version read, and a changed registry's clamping flagged ([#625](https://github.com/alexnodeland/lattice/issues/625)) ([759505c](https://github.com/alexnodeland/lattice/commit/759505ca8ff08ade1929a2b165c7d00d054311b9))
* **portalr,lattice-core,grantr:** a connected app's tools chosen in admin by checkbox, each with its risk, and Settings opened to a workspace's admins ([#661](https://github.com/alexnodeland/lattice/issues/661)) ([1cf8395](https://github.com/alexnodeland/lattice/commit/1cf83959913d9ba7b5681e861a98be76be157fc9))
* which kinds an agent's edits apply to directly in Auto, per workspace ([#1109](https://github.com/alexnodeland/lattice/issues/1109)) ([640b338](https://github.com/alexnodeland/lattice/commit/640b3385022e1edd0ed487cf787e40fe7591e08f)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)

## 0.1.0 (2026-10-17)


### ⚠ BREAKING CHANGES

* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112))
* **stackr:** access with grantr in the template: tenants from memberships, keys, and every command and read checked ([#69](https://github.com/alexnodeland/lattice/issues/69))

### Features

* **grantr:** a stored rule acts as itself, in its own workspace ([#121](https://github.com/alexnodeland/lattice/issues/121)) ([23330f4](https://github.com/alexnodeland/lattice/commit/23330f482830884063cb082f03e63a18c4eaf01b))
* **grantr:** a tenant's creation is also an entry in the deployment's audit log ([#216](https://github.com/alexnodeland/lattice/issues/216)) ([188bd33](https://github.com/alexnodeland/lattice/commit/188bd334dcf71bfd5739b5d84ba1b284f9f77437))
* **grantr:** grantr's core: the model, roles, groups, keys, checks, hooks and the audit log ([#54](https://github.com/alexnodeland/lattice/issues/54)) ([b17bed9](https://github.com/alexnodeland/lattice/commit/b17bed90da19750e13b590507a6c5cd43eb88633))
* **grantr:** members list the workspaces they may open ([#85](https://github.com/alexnodeland/lattice/issues/85)) ([fd62b36](https://github.com/alexnodeland/lattice/commit/fd62b36f0f00d90bf6cd3a5f317d4dd0d5738e4b))
* **grantr:** portalr's admin reads, for a tenant's owners and admins and for operators ([#89](https://github.com/alexnodeland/lattice/issues/89)) ([c4cfc72](https://github.com/alexnodeland/lattice/commit/c4cfc720d75e73a54583ddfb1d827f8f11d1b446))
* **grantr:** provision_tenant gives a tenant the admins it lacks ([#76](https://github.com/alexnodeland/lattice/issues/76)) ([4cc7b31](https://github.com/alexnodeland/lattice/commit/4cc7b31dfd2230a5dabdf9880bf944129b4c5b54))
* **grantr:** read the audit log from its end, with before_seq and last ([#176](https://github.com/alexnodeland/lattice/issues/176)) ([3350daa](https://github.com/alexnodeland/lattice/commit/3350daa165194dee07e9007880c550829ead9330))
* **grantr:** restrict a thread or artifact, and hide it from who holds nothing on it ([#94](https://github.com/alexnodeland/lattice/issues/94)) ([68f7b1a](https://github.com/alexnodeland/lattice/commit/68f7b1ac798ecc67d361fc78560e368d63c24194))
* **grantr:** SQL storage, the admin API, and telemetry ([#60](https://github.com/alexnodeland/lattice/issues/60)) ([d75c4f7](https://github.com/alexnodeland/lattice/commit/d75c4f796ecb0ea2c87a3084a8e6ed1e1d342f11))
* **grantr:** the application installs the rules people accept ([#108](https://github.com/alexnodeland/lattice/issues/108)) ([3353706](https://github.com/alexnodeland/lattice/commit/335370646df4db8b1e668a0213afec7154359d24))
* **grantr:** the application lists tenants and workspaces, and writes for code rules ([#99](https://github.com/alexnodeland/lattice/issues/99)) ([22ee3e0](https://github.com/alexnodeland/lattice/commit/22ee3e04b12a6ee65fba26eb5c68a6d26ef6e7ad))
* **grantr:** the audit log, read by type and by actor ([#152](https://github.com/alexnodeland/lattice/issues/152)) ([20e4451](https://github.com/alexnodeland/lattice/commit/20e44513e8fa47b8d8cc6b2ad4590a8aba07329e))
* **grantr:** the catalog, read: the roles a tenant's admins grant, and what a custom role may hold ([#165](https://github.com/alexnodeland/lattice/issues/165)) ([ba086a6](https://github.com/alexnodeland/lattice/commit/ba086a6cdd7d4ea6313646933d2e9036bd9116a9))
* **grantr:** the runtime's roles, the deployment's own tools, and the role matrix ([#65](https://github.com/alexnodeland/lattice/issues/65)) ([6c71b8f](https://github.com/alexnodeland/lattice/commit/6c71b8f5ac865c16e46ddc3f6f54c12018253808))
* **lattice-core:** the SQL helpers the libraries' storages share, behind a sql extra ([#186](https://github.com/alexnodeland/lattice/issues/186)) ([9b6a571](https://github.com/alexnodeland/lattice/commit/9b6a57144d9efdfd933d66b80a86a87ce7e10a8c))
* **portalr:** portalr's and grantr's marks, and ui's tokens and first primitives ([#64](https://github.com/alexnodeland/lattice/issues/64)) ([cbbeb93](https://github.com/alexnodeland/lattice/commit/cbbeb93f5d39e85e7380c8ed8895f256ca8493bd))
* **reflexr:** row-level security in the SQL adapter, with the scheduler's reads on the owner's engine ([#102](https://github.com/alexnodeland/lattice/issues/102)) ([4cb71dd](https://github.com/alexnodeland/lattice/commit/4cb71dd6565955fce589be41f0e0df030a1bc63f))
* **relayr:** row-level security in the SQL ledger, with the followers' start on the owner's engine ([#106](https://github.com/alexnodeland/lattice/issues/106)) ([437ae71](https://github.com/alexnodeland/lattice/commit/437ae71cd2432e0268a189d04cf466501967e3a1))
* **relayr:** the inbound adapter, with followers, the ledger and the bridged types ([#70](https://github.com/alexnodeland/lattice/issues/70)) ([ce51f03](https://github.com/alexnodeland/lattice/commit/ce51f03ca740b903b50c6996ae86b3ab20893c18))
* row-level security in grantr's and artifactr's SQL adapters ([#100](https://github.com/alexnodeland/lattice/issues/100)) ([bc0ab8e](https://github.com/alexnodeland/lattice/commit/bc0ab8eb7abeba0fd5923eb4afa1d93ddb3cd11a))
* **stackr:** access with grantr in the template: tenants from memberships, keys, and every command and read checked ([#69](https://github.com/alexnodeland/lattice/issues/69)) ([6167895](https://github.com/alexnodeland/lattice/commit/61678950c2338d59d1afa65b3b15911ada84579f))


### Bug Fixes

* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112)) ([77b7ab3](https://github.com/alexnodeland/lattice/commit/77b7ab3ef0e3ddbfe1da8f4fbff22aa03a6ba0b5))
* **reflexr:** an epoch fences each attempt, so a cancelled and retried one cannot record ([#247](https://github.com/alexnodeland/lattice/issues/247)) ([bc2adfe](https://github.com/alexnodeland/lattice/commit/bc2adfe496dbba06fb483c71fee57f1457e40354))
* the thread claim and owner bugs that TLC and the stateful tests found ([#271](https://github.com/alexnodeland/lattice/issues/271)) ([907cad9](https://github.com/alexnodeland/lattice/commit/907cad95a5ae8e5e2c9c168085168c3137266227))
* what ty's trial found: missing [@override](https://github.com/override), context managers' types, and a callable without a name ([#62](https://github.com/alexnodeland/lattice/issues/62)) ([6bca781](https://github.com/alexnodeland/lattice/commit/6bca78150eed3fc1d9e7822206421c4f6df28313))

## Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
