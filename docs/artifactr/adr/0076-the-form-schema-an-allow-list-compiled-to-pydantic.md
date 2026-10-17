# ADR-0076: The form schema, an allow-list compiled to Pydantic

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) (O4) chose a JSON Schema 2020-12 subset with separate UI hints, validated in Python with no third-party validator, by compiling a `FormSchema` to a Pydantic model once. Models write the schema, so a refusal must say what to change; portalr renders each error under its field.

## Decision

- **`FormSchema` is a Pydantic model of the subset, strict and closed.** A keyword outside it is an extra input, refused at its place. The keywords a model is most likely to write, `$ref`, `$defs`, `pattern`, `if`, `then`, `else`, `allOf`, `anyOf` and `not`, are refused by name before anything else is read (`REFUSED_KEYWORDS`), as are a nested object and `format: "password"`, with reasons of their own.
- **A property is told apart by its `type`, or as choices by `enum` or `oneOf`,** whose `type` is implied. `integer` is a `number` property with whole values. An array holds choices only.
- **A `default` must be a value its property takes,** so portalr never prefills an invalid value, and **bounds no value meets are refused:** a `minLength` over its `maxLength`, a lower bound over an upper one (or equal, with either exclusive), a `minItems` over its `maxItems`, or over the number of choices when each is chosen once.
- **A property's name is an identifier:** a letter or `_`, then up to 63 letters, digits, `_` or `-`, and never `__proto__`, `constructor` or `prototype`, which JavaScript objects treat apart. Any such name is a field, whatever Python makes of it.
- **Each property names the type its values are validated as,** and the schema compiles them into a strict model, once for each schema, kept by its JSON for the 256 schemas used last, whose fields have names of their own and the properties' names as aliases. Any property name is a field, and an error's `loc` is `[name]`; values that aren't an object, or are over the limit, are refused at `[]`. The values are returned as given.
- **A string is at most 10,000 characters whatever its `maxLength` says.**
- **A schema is stored as JSON Schema,** with what was left out still left out and `type`, `required` and `additionalProperties: false` written, and reads back unchanged. The 32 KB limit is a form's whole, its title, schema and hints, measured as stored, so a form that passed once passes every read; a title is at most 200 characters.
- **The refusal's message names every error,** with Pydantic's errors as its `errors`; the agent's tools give it to the model as the retry. A refused schema's `loc` is Pydantic's, with the property's kind after its name, as Pydantic tags a union's member.
- **`UiHints`** hold `fields` (a `widget`, `placeholder` and `help` per property), `order`, `sections` and `submit_label`, and nothing else; a hint must name a property of the schema, and a widget must fit it (`textarea` a string, `select` choices, `checkbox` a boolean).

## Options considered

| Option | For | Against |
|---|---|---|
| **Pydantic models of the subset, compiled per schema (chosen)** | No new dependency; Pydantic's errors carry `loc`; the wire schema comes from the same models | Pydantic's tags appear in a refused schema's `loc` |
| A walk over the raw JSON | Errors exactly as we want them | A validator of our own to keep, beside the TypeScript one |
| `jsonschema` | Full JSON Schema | A third-party validator the RFC excludes, and keywords no model needs |

## Consequences

- Easier: one model gives the validator, the stored shape and portalr's types.
- Harder: the TypeScript side repeats the subset; `tests/ui/vectors/forms.json` holds the cases both sides test.
