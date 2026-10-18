# Notices: the Plane recipe

`compose.yaml` runs these images as their publishers build them, unmodified. lattice (MIT) calls Plane only over its REST API, and vendors, patches and links none of their code. A deployment that modifies Plane takes on the AGPL's obligations for it. This is a reading of the licences, not legal advice.

| Image | Version | Licence | Source |
|---|---|---|---|
| `makeplane/plane-backend` | v1.4.2 | AGPL-3.0-only | <https://github.com/makeplane/plane/tree/v1.4.2> (`apps/api`) |
| `makeplane/plane-frontend` | v1.4.2 | AGPL-3.0-only | <https://github.com/makeplane/plane/tree/v1.4.2> (`apps/web`) |
| `makeplane/plane-admin` | v1.4.2 | AGPL-3.0-only | <https://github.com/makeplane/plane/tree/v1.4.2> (`apps/admin`) |
| `makeplane/plane-proxy` | v1.4.2 | AGPL-3.0-only, around Caddy (Apache-2.0) | <https://github.com/makeplane/plane/tree/v1.4.2> (`apps/proxy`), <https://github.com/caddyserver/caddy> |
| `postgres` | 15.7-alpine | PostgreSQL | <https://www.postgresql.org/ftp/source/>, image <https://github.com/docker-library/postgres> |
| `valkey/valkey` | 7.2.11-alpine | BSD-3-Clause | <https://github.com/valkey-io/valkey>, image <https://github.com/valkey-io/valkey-container> |
| `rabbitmq` | 4.1.4-alpine | MPL-2.0 | <https://github.com/rabbitmq/rabbitmq-server>, image <https://github.com/docker-library/rabbitmq> |

Each image also holds its base system's packages, under their own licences.
