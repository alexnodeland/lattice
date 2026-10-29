# AGENTS.md: @portalr/client

[web/AGENTS.md](../AGENTS.md) applies; this adds what is specific to `client`.

- `src/generated/` is generated from the packages' committed OpenAPI and JSON Schema documents by `moon run client:types` ([ADR-0010](../../../../docs/portalr/adr/0010-the-client-generated-types-and-resumable-stores.md)). Never edit it; regenerate after any package's `schema` task and commit the result. A drift test fails otherwise.
- Don't re-declare a type the generated files have; import it.
- `typecheck` uses the root's TypeScript 7; the package's own `typescript` (6) exists only for openapi-typescript. Don't remove it.
- `moon run client:api` runs the client against docplan and oncall (`api/`); it needs Docker.
