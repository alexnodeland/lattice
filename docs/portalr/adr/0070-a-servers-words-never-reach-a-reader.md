# ADR-0070: A server's words never reach a reader

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Builds on [ADR-0065](0065-empty-error-and-not-found-states.md), and settles [lattice #552](https://github.com/alexnodeland/lattice/issues/552).

## Context

A refusal's body is the server's: its `detail`, a rejection's `message`, Pydantic's `msg`. It can hold what a tenant shouldn't read, such as another person's name, an internal address or a stack's words. It can also be long, run over lines, or carry markup or direction controls.

`failureSaid` already said a read's failure in the kit's own words (ADR-0065). But several other places still put the server's text on screen:

- the client's `reasons`, which every refused command shows;
- a form's errors under its fields;
- the UIs' start-up and paging failures, and the deployment tools' failure;
- the runs page's fallback;
- the settings page's refusal;
- a closed stream's error frame, signing in (Supabase Auth's own message), and a mini app's refused tool call.

## Decision

- **A reader is told a sentence of the kit's own,** chosen by the refusal's known reason code, else its status, else a generic one. The client's `refusalSaid` decides it, for every refused command's words (`reasons`) and for a refused read, whose `Refused` carries it as `said`. ui imports none of the client's values ([ADR-0015](0015-the-chat-components-and-streamdown.md)), so `failureSaid` shows a read's `said`, and the generic sentence for anything else.
  - **Codes:** `forbidden`, `not_found`, `not_enabled`, `invalid_state`, `version_conflict`, `validation_failed`, `artifact_busy`, `over_quota`, `too_slow` and `invite_failed`.
  - **Statuses:** 401, 403, 404, 413, 422, 429 and 5xx.
  - A command's `forbidden` says "You may not do this here.", since it was an action and not a read.
- **Values that aren't valid are told where they are,** as the owner decided: the kit's sentence and the fields' paths, from each error's `loc`, such as "What was asked for isn't valid: rule.when." Never the server's `msg`.
  - A path starts after where in the request it is (`body`, `query`) and after a command frame's `command` and its type.
  - A path is told only if each of its parts is a plain name or index of at most 32 characters, none of them shaped like a secret (`token`, `password`, `api_key`, a provider key's prefix), and it has at most six parts. At most five paths are told, of at most 160 characters in all. So no text of the server's comes through one, nor a key named or shaped like a secret. A bare run of hex or base64 in a key is not recognized, and is told. The fields' paths are read in a chunk loaded only for such a refusal; if it can't load, the sentence is said without them.
  - A form's own fields say the kit's words under them ("This isn't valid.", or the kit's words for a missing value, a format or a choice); what names no field says the kit's sentence above them.
- **Everything else goes through `FailureAlert`:** the UIs' start-up failures, an audit log's earlier page, and the deployment's tools. Each says what didn't happen, then the kit's sentence.
- **`ConfirmDialog` shows its caller's words,** which are the kit's own: a refused command's are `refusal`'s. Anything thrown that isn't an `Error` gets the kit's sentence.
- **The settings page tells a refused value why from the row it already shows,** not from grantr's message: a number over the ceiling, the ceiling and who set it; any other value, that it isn't allowed; a 403, that it can't be changed here.
- **A closed stream says it ended, signing in says the email and password don't match (or too many tries, or the generic sentence), and a mini app's refused `set_state` is told only a patch's own refusal,** which names nothing but what the app sent.
- **One exception, kept on purpose: a run's own "Details".** A failed run's error, in its Details block, is shown as the run recorded it, for the person who asked for the run to see why it failed. Everything else follows this record.
- **The whole failure goes to the console of the reader's own browser,** not to a server: `failureLogged` writes it once, as one line, with a refusal's status and the server's body as JSON, and what looks like a secret taken out. It is the reader's to read and hand on.

## Options considered

- **The status and code alone, no paths:** a person who typed a rule or filled a form would learn only that something was wrong, not where. A path is a field's name and nothing more, so the owner kept it.
- **The server's message, cleaned:** markup, controls and a length can be taken out, but not what the words say.

## Consequences

- Easier: no refusal can show a tenant what a server said, whatever it says.
- Known gap: reflexr reports a stored rule's problems as strings, with no `loc`, so the rule editor says only that the rule isn't valid, not which field ([lattice #665](https://github.com/alexnodeland/lattice/issues/665)).
- Harder: a message that was useful, such as "acme exists" or a ceiling's layer, is now the kit's sentence. Where a reader needs more, the code or a typed field carries it, as `artifact_busy`, `over_quota` and the settings' ceiling do. A new code needs its sentence here.
