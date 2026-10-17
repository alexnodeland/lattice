# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
