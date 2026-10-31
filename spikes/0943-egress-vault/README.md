# Spike #943 and #942: Envoy's rebinding pinning, `ext_authz` injection and Supabase Vault

The findings of a time-boxed spike for M2. It checks the riskiest claims RFC-0011 lists as
Unverified before its phase 3 (stores) and phase 4 (egress) are built on them
([#943](https://github.com/alexnodeland/lattice/issues/943),
[#942](https://github.com/alexnodeland/lattice/issues/942)). This folder can be deleted once
those phases land.

The spike's code is on the branch
[`spike/0943-egress-vault-code`](https://github.com/alexnodeland/lattice/tree/spike/0943-egress-vault-code/spikes/0943-egress-vault). That code is not maintained: it isn't imported, tested or
shipped, and nothing from it should be copied into a package's `src/`.

Run on 2026-10-31, on macOS (Apple silicon) with Docker Desktop (Engine 29.4), as one Compose project
(`spike0943-<token>`) on one network with an explicit subnet, `198.18.94.0/24`. That is a
benchmarking range, in none of RFC-0011's refused ranges, so it stands in for "the internet".
It was removed by its exact name afterwards. Versions:

| Image | Version | Pinned by |
|---|---|---|
| `public.ecr.aws/supabase/postgres` | `17.6.1.171@sha256:658d1c9b…`, `supabase_vault` 0.3.1 | Supabase CLI 2.118.0 (stackr's `versions.env`) |
| `envoyproxy/envoy` | `v1.40.2@sha256:8de97e65…` | the spike (stackr pins no Envoy) |
| `curlimages/curl` | `8.22.0@sha256:58adaa4e…` | stackr's `compose.yaml` |
| `python` | `3.13-slim@sha256:70729b46…`, grpcio 1.76.0 | the spike |
| smokescreen | built from `stripe/smokescreen@336cb344` (2026-10-28) on `golang:1.26-alpine` and `alpine:3.21` | the spike: there is no published image |

## The answers

| # | Question | Answer |
|---|---|---|
| 1 | Can Envoy connect only to the address the authorizer checked? | **Holds**, with an `ORIGINAL_DST` cluster addressed by the authorizer's answer, or with the dynamic forward proxy fed that answer through filter state. The plain dynamic forward proxy **doesn't**: it resolves again and connected to `127.0.0.1` on every try. smokescreen isn't needed, but refuses the same rebinding. |
| 2 | Does `ext_authz`'s allow response set upstream headers when Envoy originates TLS, and does its metadata reach the access log? | **Holds**, for a plain-HTTP forward-proxy request: the credential is set, every caller credential header is stripped, SNI and SAN come from the host, and tenant, workspace, purpose and the checked address are in the JSON access log. |
| 3 | Supabase Vault: its API, a tenant-checking security-definer function, the key outside `pg_dump` | **Partly.** The API is as 0011 assumes, the function works, and the key stays out of the dump. But `postgres` and `service_role` can read the view as shipped, and only a superuser can take `service_role` off. Above all, **stackr's production recipes run no Vault**: the single-host recipe uses `postgres:17.11-alpine` and the AWS recipe RDS 17, and neither has `supabase_vault`. |

## What was built

```
client (curl)  ── Proxy-Authorization: Bearer <caller token> ──▶ Envoy 1.40.2
                                                                  │ ext_authz (HTTP; gRPC for CONNECT)
                                                                  ▼
                                    authorizer ── resolves itself ──▶ dns (flips per query)
                                     refuses RFC-0011's ranges; on allow answers
                                     x-lattice-upstream: <checked ip>:<port>, the credential,
                                     the headers to strip, and x-lattice-* as dynamic metadata
                                                                  │
  :10000 odst    ext_authz → router → ORIGINAL_DST cluster (address = x-lattice-upstream)
  :10001 dfp     ext_authz → dynamic_forward_proxy → router   (the control: Envoy resolves again)
  :10002 cred    as odst, the cluster originating TLS: question 2
  :10003 dfpin   ext_authz → set_filter_state(envoy.upstream.dynamic_host = checked ip) → DFP
  :10004 tunnel  CONNECT, gRPC ext_authz → ORIGINAL_DST
                                                                  ▼
             upstream 198.18.94.20 (:80 says PUBLIC, :443 TLS echoes its headers)
             decoy on Envoy's own 127.0.0.1:80 (says INTERNAL): what a rebinding reaches

db, db2: supabase/postgres 17.6.1.171, for question 3
```

The DNS server answers `<name>.rebind.test` with `198.18.94.20` on the 1st, 3rd, … query for
that name and `127.0.0.1` on the 2nd, 4th, …, with TTL 0, and logs who asked. Each request uses
a fresh name, so no cache hides the flip, and the authorizer always asks first. The test is
deterministic: "did Envoy connect to an address the authorizer didn't return?"

The files, all on the spike's branch:

| File | What it is |
|---|---|
| [`compose.yaml`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/compose.yaml) | The one project: `db`, `db2` (profile `restore`), the egress services (profile `egress`), smokescreen (profile `smokescreen`) |
| [`egress/envoy.yaml`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/envoy.yaml) | Envoy's configuration, the five listeners; `render.py` resolves its anchors into `envoy.json` |
| [`egress/servers.py`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/servers.py) | The flipping DNS server, the HTTP authorizer, the upstream and the decoy, standard library only |
| [`egress/grpc_authz.py`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/grpc_authz.py) | The same policy over gRPC `ext_authz`, protobuf by hand, for CONNECT |
| [`egress/rebind.sh`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/rebind.sh), [`tunnel.sh`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/tunnel.sh), [`inject.sh`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/inject.sh), [`smokescreen.sh`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/smokescreen.sh) | The runs; each `*.out` beside them is what it printed |
| [`egress/Dockerfile.smokescreen`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/egress/Dockerfile.smokescreen) | smokescreen built from source at a pinned commit |
| [`vault/isolation.sql`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/vault/isolation.sql), [`dump-check.sh`](https://github.com/alexnodeland/lattice/blob/spike/0943-egress-vault-code/spikes/0943-egress-vault/vault/dump-check.sh) | Question 3; `isolation.out`, `dump.out` and `restore.out` are their output |

## 1. DNS rebinding: holds, with the cluster addressed by the authorizer

The authorizer resolves the host, checks the address, and answers the address it checked:

```yaml
# ext_authz (HTTP service)
authorization_response:
  allowed_upstream_headers:
    patterns: [{exact: x-lattice-upstream}, {exact: x-lattice-upstream-ip}, {exact: authorization}]
  dynamic_metadata_from_headers:
    patterns: [{prefix: x-lattice-}]

# the cluster: Envoy never resolves the name, it connects where the header says
- name: odst
  type: ORIGINAL_DST
  lb_policy: CLUSTER_PROVIDED
  original_dst_lb_config: {use_http_header: true, http_header_name: x-lattice-upstream}
```

Five fresh names through each listener (`egress/rebind.sh`, abridged from `rebind.out`):

```
== listener 10000          (ORIGINAL_DST)
r1-10000-….rebind.test -> PUBLIC          … all five PUBLIC
== listener 10001          (dynamic forward proxy, the control)
r1-10001-….rebind.test -> INTERNAL (served by 127.0.0.1)          … all five INTERNAL
== listener 10003          (DFP, host taken from the authorizer's answer)
r1-10003-….rebind.test -> PUBLIC          … all five PUBLIC
== caller-supplied x-lattice-upstream: 127.0.0.1:80, to an allowed host
listener 10000 -> PUBLIC
listener 10003 -> PUBLIC
```

The DNS log shows why. Through `dfp`, Envoy (`198.18.94.2`) asked after the authorizer
(`198.18.94.10`) and got the flipped answer. Through `odst` and `dfpin`, Envoy never asked:

```
{"client": "198.18.94.10", "name": "r1-10001-….rebind.test", "answer": "198.18.94.20", "n": 1}
{"client": "198.18.94.2",  "name": "r1-10001-….rebind.test", "answer": "127.0.0.1",    "n": 2}
{"client": "198.18.94.10", "name": "r1-10000-….rebind.test", "answer": "198.18.94.20", "n": 1}
```

The access log shows it too: the address checked against the one connected to.

```
{"listener":10001,"authority":"r1-10001-….rebind.test","checked":"198.18.94.20","upstream_host":"127.0.0.1:80","code":200,…}
{"listener":10000,"authority":"r1-10000-….rebind.test","checked":"198.18.94.20","upstream_host":"198.18.94.20:80","code":200,…}
```

Four more findings:

- **CONNECT needs the gRPC `ext_authz` service** (`tunnel.out`, `connect-http-authz.out`). With
  the HTTP service, Envoy sends a CONNECT's check to the authorizer *as* a CONNECT. Its own async
  client answers that 503, so the filter fails closed (`ext_authz_error`, 403) even when the
  authorizer said allow. With `grpc_service` and the same `ORIGINAL_DST` cluster, CONNECT
  tunnels are checked and pinned: the three rebinding names reached PUBLIC, `private.test` got
  403, and TLS through the tunnel to `api.upstream.test:443` worked end to end.
- **Don't strip the routing header on the route.** A route's `request_headers_to_remove: [x-lattice-upstream]`
  runs before `ORIGINAL_DST` picks the host. That leaves the cluster nothing, so it answers 503:
  `original_dst_load_balancer: No downstream connection or no original_dst`. So a missing header
  fails closed, and does not fall back to some other address. Strip it in the cluster's upstream
  HTTP filters (`header_mutation` before `upstream_codec`), which run after the host is chosen.
  That worked (`inject-stripped.out`).
- **A caller can't steer it.** A caller-sent `x-lattice-upstream: 127.0.0.1:80` is overwritten
  by the authorizer's answer, because `allowed_upstream_headers` overwrites.
- **The dynamic forward proxy pinned through filter state also holds** (listener 10003:
  `set_filter_state` puts the checked IP in `envoy.upstream.dynamic_host`, and the DFP filter has
  `allow_dynamic_host_from_filter_state: true`). It is a DNS cache that only ever holds IP
  literals, though: `ORIGINAL_DST` does the same with fewer parts.

**smokescreen**, for the record (`smokescreen.out`, `smokescreen-flipped.out`): it resolves once
per request and dials the address it checked. For a name whose answer had already been taken by
an earlier check, so smokescreen got `127.0.0.1`, it refused:

```
f1-….rebind.test -> Egress proxying is denied to host 'f1-….rebind.test': no valid IP found among
resolved addresses - 127.0.0.1 denied by rule 'Deny: Self Connection'. [HTTP 407]
```

It has no published image (Docker Hub 404, and GHCR refuses an anonymous pull token), so stackr
would build it, as 0011 guessed. It wasn't tried behind Envoy, because the fallback isn't needed.

## 2. Credential injection: holds

The caller sends a plain-HTTP forward-proxy request to listener 10002 with a reference, its own
`Authorization` and an `x-api-key`. The authorizer answers `authorization: Bearer <value>` (set,
overwriting) and `x-envoy-auth-headers-to-remove: proxy-authorization,x-lattice-secret,x-api-key`
(plus `authorization` when nothing replaces it). The cluster originates TLS:

```yaml
upstream_http_protocol_options: {auto_sni: true, auto_san_validation: true}
transport_socket: {name: envoy.transport_sockets.tls, … validation_context: {trusted_ca: {filename: /certs/ca.crt}}}
```

What the TLS upstream received (`inject-stripped.out`, after the upstream filter strips the
routing headers):

```
curl -x http://envoy:10002 --proxy-header 'Proxy-Authorization: Bearer tok-litellm-a' \
  -H 'X-Lattice-Secret: sec_0123456789abcdef' -H 'Authorization: Bearer caller-own' \
  -H 'x-api-key: caller-key' http://api.upstream.test/v1/models
{"tls": true, "sni": "api.upstream.test",
 "headers": {"host": "api.upstream.test", "user-agent": "curl/8.22.0", "accept": "*/*",
             "x-forwarded-proto": "http", "x-request-id": "…",
             "authorization": "Bearer sk-INJECTED-BY-PROXY"}}
```

The access log line, with the authorizer's dynamic metadata (`inject.out`):

```
{"listener":10002,"authority":"api.upstream.test","code":200,"upstream_host":"198.18.94.20:443",
 "checked":"198.18.94.20","tenant":"tenant-a","workspace":"ws-1","purpose":"litellm","bytes_sent":415,"duration_ms":54}
```

Also shown in `inject.out`, `tunnel.out` and `san.out`:

- The response to the caller carries no credential.
- An unknown reference gets 403 (`no such secret for this tenant`). With no reference, the
  caller's `Authorization` is removed and nothing replaces it.
- A host whose certificate doesn't match is refused: `public.test` through 10002 gave 503, with
  `cluster.odst_tls.ssl.fail_verify_san: 1`.
- **The authorizer down refuses everything**: with it stopped, all four HTTP listeners answered
  403 (`UAEX`, after about 1 s, the authorizer cluster's connect timeout), since `failure_mode_allow: false`. That is one of phase
  4's exit criteria, met by configuration alone.
- Without `suppress_envoy_headers: true` on the router, Envoy adds `x-envoy-expected-rq-timeout-ms`
  upstream. `x-forwarded-proto: http` and `x-request-id` still reach the destination.

## 3. Supabase Vault: partly

**The API is as 0011 assumes** (`supabase_vault` 0.3.1, installed in the image's `postgres`
database, owned by `supabase_admin`):

```
vault.create_secret(new_secret text, new_name text, new_description text, new_key_id uuid) → uuid   security definer
vault.update_secret(secret_id uuid, new_secret text, new_name text, new_description text, new_key_id uuid) → void   security definer
vault.decrypted_secrets   view over vault.secrets: convert_from(vault._crypto_aead_det_decrypt(…, key_id => 0, …))
```

pgsodium 3.1.8 is available but not installed. Vault 0.3 no longer needs it.

**A security-definer function can check the tenant first and keep the application's role off
the view**, run as `vault/isolation.sql` (`isolation.out`). It used a `lattice_app` role (not a
member of any Supabase role), a `lattice.lattice_secrets` table with `lattice_core.sql`'s tenant
policy on `lattice.tenant_id`, and `put_secret`, `read_secret` and `rotate_secret` functions
owned by `postgres`, with `search_path = ''`:

```
tenant-a reads its own        → TOKEN-OF-TENANT-A
tenant-a reads tenant-b's ref → ERROR:  no such secret for this tenant
no tenant set                 → ERROR:  no tenant
rotate (vault.update_secret)  → TOKEN-OF-TENANT-A-v2
lattice_app: select from vault.decrypted_secrets / vault.secrets, call _crypto_aead_det_decrypt
                              → ERROR:  permission denied for schema vault (each)
```

But as the image ships it, two roles can read everything:

```
     role      | view_select | decrypt_exec
 lattice_app   | f           | f
 anon          | f           | f
 authenticated | f           | f
 authenticator | f           | f
 service_role  | t           | t
 postgres      | t           | t
```

- `postgres` holds `SELECT … WITH GRANT OPTION` on the view, and can run the decrypt function
  directly. It must own the function (or the function's owner must have the same access), so the
  application must never connect as `postgres`.
- `service_role` (PostgREST's role for the service key) reads the view too. `postgres` can't take
  that away: its `REVOKE` runs without error and changes nothing, because `supabase_admin` made
  the grant. As `supabase_admin` (self-hosted only), the revokes worked, and the function still
  served `lattice_app`.
- The function owner (`postgres`) bypasses RLS, so the tenant check must be in the function's
  own `WHERE`, not left to the policy.
- The tenant is the one the transaction states with `set_config`, which any `lattice_app` session
  may set. The function enforces "tenant first", but the database can't verify which tenant is
  calling. That is the same trust model as `lattice_core.sql`'s RLS today.

**The key stays outside `pg_dump`** (`dump.out`, `restore.out`). The root key is a 64-hex-character
file, `/etc/postgresql-custom/pgsodium_root.key`. The image's `pgsodium_getkey.sh` creates it from
`/dev/urandom` on first start if it is missing, and `vault.getkey_script` reads it. It is not under
`PGDATA`:

```
/tmp/dump.sql: key (any case) 0, TOKEN-OF-TENANT-A 0, KEY-OF-TENANT-B 0, vault.secrets rows 2
/tmp/dumpall.sql: key (any case) 0, TOKEN-OF-TENANT-A 0, KEY-OF-TENANT-B 0, vault.secrets rows 2
files under PGDATA containing the key: 0
sec_bbbbbbbbbbbbbbbb  litellm:key  nkv49HcSOMcdUao/S+8BLfxZ0sqsa60VMv1o6urj731p5+bVO0PkAN1X2bxiQGQ=
```

The dump's `vault.secrets` rows were restored into a second database with its own key:

```
ERROR:  pgsodium_crypto_aead_det_decrypt_by_id: invalid ciphertext
```

With the first database's key file copied in and the server restarted, the same rows decrypted.

So:

- **Backups need the key, kept apart from them.** A dump is useless without it. Recreating a bare
  container without the key file makes a new key, and every existing secret becomes unreadable.
- **Vault's name and description are stored in clear.** The spike put the ref and the purpose
  there. Nothing secret may go in them.
- **Local Supabase's key is public.** Supabase CLI 2.118.0 mounts the key file from its own
  configuration (`db.root_key`). When that is unset, it uses one fixed key compiled into the CLI
  (`d4dc5b6d…`), the same on every machine, and stackr's `supabase/config.toml` sets none. That
  is fine for development, and means nothing in local Supabase's Vault is secret.
- **Production has no Vault.** The single-host recipe runs `postgres:17.11-alpine` with
  pgBackRest, whose image has no `supabase_vault` or `pgsodium` control files (checked), and the
  AWS recipe runs RDS PostgreSQL 17, which doesn't offer `supabase_vault`. Vault exists in
  stackr only behind local Supabase, or on hosted Supabase.

## What it means for RFC-0011

### Phase 3 (stores)

1. **Decide where Vault runs in production before building the adapter.** As 0011 stands
   ("Supabase Vault first … in the stack it already has"), the first adapter works only on local
   and hosted Supabase. Three ways out: the host recipe builds Postgres with `supabase_vault`, or
   uses `supabase/postgres`; the AWS recipe uses another adapter, or hosted Supabase; or a second
   adapter (a cloud KMS, T7's) moves into 0.3.0 for the recipes without Vault.
2. **Give the application its own role,** never `postgres`. Run the Vault setup as the database
   owner that can revoke `service_role`'s grants (`supabase_admin` self-hosted). On hosted
   Supabase, `service_role` keeps the view, so the service key must not leave the operator.
3. **Write the tenant check into the function's `WHERE`,** since its owner bypasses RLS. Put
   nothing secret in Vault's `name` or `description`.
4. **The contract suite's isolation test** (the phase 3 exit criterion) should include "the
   application role can't select the view, the table, or call `_crypto_aead_det_decrypt`",
   beside "tenant-b's ref is refused to tenant-a".
5. **The key is an operator secret with its own backup and rotation story:** stackr sets
   `db.root_key` (or mounts the key file) from its secrets, and the backup docs say the dump
   doesn't contain it. O7's copy command reads values through the port, so it doesn't need the
   key.

### Phase 4 (egress)

1. **Pin with `ORIGINAL_DST`, not the dynamic forward proxy.** The authorizer resolves, checks,
   and answers `ip:port` in a routing header; the cluster connects there; Envoy never resolves.
   O9's second condition is met, and **smokescreen behind Envoy is not needed**.
2. **The authorizer must speak gRPC `ext_authz`, at least for CONNECT.** 0011 has it as "a router
   behind the `fastapi` extra". An HTTP-mode authorizer can't check CONNECT, the mode 0011 keeps
   for credential-free purposes such as registries. So either the authorizer gets a gRPC
   endpoint (grpcio, beside or instead of the FastAPI router), or registries don't tunnel.
3. **Strip the routing header in the cluster's upstream filters,** not on the route. Turn on
   `suppress_envoy_headers`.
4. **Internal destinations (O10)** fit the same shape: the authorizer checks the address against
   the declared range and answers it. A static cluster per declaration may then be unnecessary
   (not tried).
5. **The exit criteria shown here, in miniature:**
   - Done: an injected credential never reaches the caller; the authorizer down refuses
     everything; the caller's credential headers are all stripped; dynamic metadata reaches the
     access log.
   - Still open: the SSRF suite, taint, `internal: true` networks and file-based xDS.

### What the results contradict or refine in 0011

- 0011's table says the dynamic forward proxy needs the authorizer to make Envoy connect where it
  checked. Right, and the plain DFP doesn't: it connects by a lookup of its own, as shown. The working
  form is "a cluster addressed by the authorizer's answer", which 0011 lists only as a fallback.
- 0011: "`ext_authz` calls … a router behind the `fastapi` extra". Not for CONNECT: the HTTP
  service can't check one.
- 0011: "Supabase Vault … in the stack it already has". Only local Supabase has it; the host and
  AWS recipes don't.
- 0011: "no role an application holds can read the view directly". True only if the application
  connects as a role of its own: Supabase's `postgres` and `service_role` can, as shipped.

## Not exercised

- **Real TLS on the internet, and HTTP/2 or HTTP/3 upstreams.** The CA and certificate were the
  spike's own, made at run time.
- **Redirects.** Envoy as a forward proxy passes 3xx to the caller, whose next request is checked
  again. Not tested.
- **IPv6, and several A records.** The authorizer took the first answer. A real one must check
  every answer, or refuse a mixed set, and answer the one it checked.
- **Taint, file-based xDS, `internal: true` networks and the SSRF suite** (other Unverified items).
- **smokescreen behind Envoy**, because it isn't needed. Hosted Supabase, whose grants may differ
  from the image's.
- **Timings.** Everything ran under Docker Desktop. The `supabase/postgres` image's server
  reported `x86_64`, so it ran emulated.

## How to run it again

From a checkout of the spike's branch, in `spikes/0943-egress-vault/`, with a random token `T`:

```bash
export T=$(openssl rand -hex 4)
egress/gen-certs.sh && uv run python egress/render.py
docker compose -p spike0943-$T up -d db
docker exec -i spike0943-$T-db psql -U supabase_admin -h localhost -d postgres -X -f /spike/isolation.sql
docker exec -e PGDATA=/var/lib/postgresql/data spike0943-$T-db sh /spike/dump-check.sh
docker compose -p spike0943-$T --profile egress --profile smokescreen up -d --build
egress/rebind.sh; egress/inject.sh; egress/tunnel.sh; egress/smokescreen.sh
docker compose -p spike0943-$T --profile restore --profile egress --profile smokescreen down --volumes --rmi local
```

`restore.out` came from a one-off: copying `vault.secrets` from `db` into `db2` (profile
`restore`), then copying the key file across.
