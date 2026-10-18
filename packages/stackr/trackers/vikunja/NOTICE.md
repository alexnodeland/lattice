# Notices: the Vikunja recipe

`compose.yaml` runs these images as their publishers build them, unmodified. lattice (MIT) calls Vikunja only over its REST API, and vendors, patches and links none of their code. A deployment that modifies Vikunja takes on the AGPL's obligations for it. This is a reading of the licences, not legal advice.

| Image | Version | Licence | Source |
|---|---|---|---|
| `vikunja/vikunja` | 2.7.0 | AGPL-3.0-or-later | <https://github.com/go-vikunja/vikunja/tree/v2.7.0> |
| `postgres` | 17 | PostgreSQL | <https://www.postgresql.org/ftp/source/>, image <https://github.com/docker-library/postgres> |

Each image also holds its base system's packages, under their own licences.
