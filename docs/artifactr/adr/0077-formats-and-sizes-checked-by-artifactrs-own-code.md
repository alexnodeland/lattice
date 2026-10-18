# ADR-0077: Formats and sizes, checked by artifactr's own code

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

The subset has formats, `date`, `date-time`, `email` and `uri`, and limits in bytes. Pydantic checks an email only through `email-validator`, a third-party dependency [lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) excludes. portalr validates the same subset in TypeScript before it sends, so each check must be one it can repeat exactly.

## Decision

- **Each format is a pattern of artifactr.ui's own**, JavaScript-compatible, its digits and spaces spelled out as JavaScript reads them and each matching the whole text: a `date` is an RFC 3339 full date on the calendar; a `date-time` is RFC 3339 with seconds and an offset (`T`, and `Z` or `±hh:mm`), so a browser's `datetime-local` value is converted before it is sent; `T` and `Z` in either case; an `email` is a local part of up to 64 characters without whitespace or `@`, `@`, and a domain of two or more dotted ASCII labels, at most 254 characters in all; a `uri` is a link a person may follow, `http://`, `https://` or `mailto:` in either case, and no whitespace.
- **`multipleOf` is artifactr.ui's own check too:** a value is a multiple when `value / multipleOf` is a whole number, exactly or to within a billionth of the quotient, which floats need and Pydantic's integer constraint can't take; a quotient too large for a float is no multiple.
- **Every number, in a schema, a value or a dashboard, is within ±(2⁵³ − 1)** (`MAX_NUMBER`), JavaScript's `Number.MAX_SAFE_INTEGER`, bounds included, so both sides read it as written and no check overflows.
- **Every limit is measured as the UTF-8 bytes of compact JSON** (`json_size`): no spaces after separators, non-ASCII characters as they are, keys in their order, as JavaScript's `JSON.stringify` writes it.

## Options considered

| Option | For | Against |
|---|---|---|
| **Small checks of our own (chosen)** | No dependency; the TypeScript side repeats them | An address valid by RFC 5321 with quoting or an IP literal is refused; an internationalised domain must be sent as punycode |
| `email-validator` through Pydantic | Thorough | A third-party validator, and checks the browser can't repeat |

## Consequences

- Easier: both sides agree on every vector.
- Harder: a `uri` of another scheme, `ftp:` or `urn:`, is refused; `javascript:` and `data:` must be.
