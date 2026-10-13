# ADR-0020: The Rules area: stored rules as reflexr's JSON, sent over its REST

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives the app a Rules area: the workspace's rules and schedules, and their status, with installing and editing them where allowed. reflexr has two kinds of rule. A code rule is registered by the application, for every workspace, and no one changes it at runtime. A stored rule is installed in one workspace at runtime, as reflexr's JSON, within the limits of the application's `StoredRules` and core's constants: it needs a throttle, a timeout, unordered runs, and a namespace and an action the application allows. `install_rule`, `update_rule` and `archive_rule` change one, the last two naming the version they replace, and grantr gives them to a workspace's admin and the tenant's owners and admins, not its editors.

reflexr's stream answers each command it can read with its result. It can't read a body that isn't a command, such as a rule's JSON with a field of the wrong type, and it answers that with an error frame that names no command. A command sent that way would never settle, and a rule typed by hand is often wrong. Its REST route, `POST /workspaces/{id}/commands`, answers every request: with the command's result, its rejection, or FastAPI's account of where the body is wrong.

## Decision

- **The Rules area lists every rule reflexr has for the workspace,** code rules first, each with its origin, a stored rule's version, whether it is enabled, how far behind the log it is, and its dead letters; and the schedules that tick into the workspace, with their next and last ticks, in the reader's time zone. A rule's page shows its description, its origin and its JSON.
- **A stored rule is written as reflexr's JSON,** in a text field: a new one starts from a skeleton of what every stored rule needs, and an existing one from its current version. The browser checks only that it is JSON. reflexr checks the rest, and its reasons are what the field says: the problems `check_stored` lists, a conflict's message, or where in the rule FastAPI found it wrong. The app holds none of reflexr's limits, which the application sets.
- **Rule commands go over reflexr's REST,** through `client`'s `createCommands`, which every route reaches from the router's context beside its queries. Every answer is one: a server that can't be reached is a refusal with status 0, not a thrown error, so the field keeps the person's text; and a refusal because no one is signed in ends the session, as a refused read does. The rest of the app's commands stay on the streams.
- **An update or archive names the version it replaces:** the version the editor opened, or last saved or loaded. A change made over someone else's is refused with the version the rule is at, and the person's text stays in the field. The page then says which version was saved since, with a button that loads it. A Save whose rule has another name is refused in the browser: renaming is installing a new rule.
- **What the logs say changed, once live, makes stale the reads it changed:** `WorkspaceStreams` hears each live event of both streams (`Stream.onLiveEvent`) and invalidates `client`'s `stale` keys for it, so the list, a rule's page and the schedules' ticks are read again as they change, by one mechanism. The replay that catches a store up isn't heard, since the screen's reads are as new.
- **An archived or unknown rule's page says "Rule not found",** as an artifact's does.
- **Install, Save and Archive show where grantr allows them,** asked once per screen as ADR-0018's `allowedIn` does: Install on the workspace, Save and Archive on the rule itself, as reflexr asks grantr of them. A code rule has none of them.
- **The rule editors hold their text in state, not in the form,** since React resets a form after its action, and a field whose default changed between renders took the old text back.
- **The test application allows stored rules** in the `tickets` namespace, which run `triage`, and maps a stored rule's runs to grantr's `RulePrincipal`, as the template does; ADR-0018 recorded it with none. A daily schedule, `portalr:digest`, ticks into every workspace, for the area to list. A test installs a rule as alice, the tenant's owner, sees its run succeed, and has bob, an editor, refused.
- **The scenarios install rules of their own,** each named afresh, and the Runs scenarios read only `portalr:triage`'s runs, since a stored rule another scenario installed may match their tickets too.

## Options considered

| Option | For | Against |
|---|---|---|
| **Rule commands over REST (chosen)** | An answer to every command, and where a body is wrong | A second way to send commands |
| Rule commands over the stream | One way to send commands | A malformed rule never settles: the error frame names no command |
| Have reflexr's stream name the command in its error frame | One way, and an answer | A change to reflexr's protocol for one client's need, and an id to read from a body that isn't a command |
| **The rule as JSON in a text field (chosen)** | Every field reflexr has, as its JSON Schema documents it; nothing to keep in step | A person must know the JSON |
| A form for each field | Guided | A form to keep in step with reflexr's rules, and every condition and pattern to build |
| **reflexr's checks, shown on the field (chosen)** | The application's limits in one place | A round trip to learn of a problem |
| Check in the browser too, from the JSON Schema | Faster | A validator in the bundle, and the application's limits copied |

## Consequences

- Easier: the admin UI, and any later form, sends commands that need a sure answer through `createCommands`.
- Harder: writing a rule needs reflexr's JSON. The skeleton and reflexr's reasons help, and a guided form can come later.
- Harder: the list's lag and dead letters are read when the page opens, and when a rule changes, not as the reactor moves.
- Harder: an event that lands between a screen's read and the end of the stream's replay isn't heard, so that read stays as it was until the next change.
