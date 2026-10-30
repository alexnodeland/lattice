# Protocol JSON Schema

[`schemas/artifactr.v1.json`](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/schemas/artifactr.v1.json) is the JSON Schema of every frame in the [thread protocol](../protocol.md). Its two properties are `client`, any frame a client sends, and `server`, any frame a server sends; `$defs` holds every frame, command, event and live event they refer to.

The schema is generated from the protocol's Pydantic models in `artifactr.core`, which are the source of truth, and checked in. A test fails if the checked-in file drifts from the models; regenerate it with `moon run artifactr:schema`, which runs, in `packages/artifactr/`, the module `artifactr.core.schema` and writes only what it prints to the file (`python -m artifactr.core.schema` prints the schema):

```bash
uv run python ../../scripts/generate.py schemas/artifactr.v1.json artifactr.core.schema
```

## Generating client types

Frontends generate their types from the schema rather than writing them by hand. For TypeScript, for example, with [json-schema-to-typescript](https://github.com/bcherny/json-schema-to-typescript):

```bash
npx json-schema-to-typescript schemas/artifactr.v1.json > src/artifactr.d.ts
```

Within `artifactr.v1`, changes are additive only: new optional fields and new event types. Clients should ignore fields they do not know, and keep an event of an unknown type as an opaque envelope, since it still carries a `seq`.

## The schema

??? abstract "`schemas/artifactr.v1.json`"

    ```json
    --8<-- "packages/artifactr/schemas/artifactr.v1.json"
    ```
