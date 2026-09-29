# ADR-0011: Scores shared with the libraries

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Amends [ADR-0006](0006-ports-and-adapters.md) with a port, `ScoreConfigStore`, and a wider `Score`.

## Context

artifactr (its ADR-0038) and reflexr (its ADR-0025) each carry a `scores` package that turns people's feedback into scores:

- a mapping from a feedback type to one `ScoreConfig` per field, and from a feedback value to one score per field, named `{type}.{field}` and typed by the field
- two ports: `ScoreSink` (`send(score)`) and `ScoreConfigStore` (`names()`, `create(config)`)
- a `FeedbackMirror` that follows a workspace's log and sends each piece of feedback's scores to a sink, and `sync_score_configs`
- Langfuse adapters of both ports, in their `[langfuse]` extras

The two mappings are identical but for their imports. evalr has its own `Score`, `ScoreSink` (`record(scores)`) and `scores(verdict)`, built on `verdict_fields`, following the same naming so that evaluators' scores sit beside people's. Three copies of one mapping drift, and a drift splits one score into two in Langfuse. [Issue #17](https://github.com/alexnodeland/evalr/issues/17) proposed one copy. On 2026-09-29 the maintainer decided:

- The field-to-score mapping and the `Score`, `ScoreSink` and `ScoreConfigStore` ports move into `evalr.core`.
- The libraries' `[langfuse]` and `[evals]` extras depend on evalr and drop their copies.
- Mirroring feedback onto traces and sessions (the mirrors, and their Langfuse adapters) stays in each library.
- Until evalr is on PyPI, the libraries pin it by git revision.

The copies disagreed in the details:

| | The libraries | evalr |
|---|---|---|
| A field evaluators cannot judge (a list, a union) | Not scored | `UnsupportedField` |
| An `int`'s exclusive bound, `gt=0` | A minimum of 0 | A lower bound of 1 |
| A yes or no | `1.0` or `0.0` | `True` or `False` |
| An empty string | No score | A score of `""` |
| A long text | Cut at 500 characters | Kept whole |
| Where a score is | A trace or a session, when given, with metadata about its source | A trace and a span, with the evaluator, its version and the confidence |
| The sink | `send(score)` | `record(scores)` |

## Decision

**evalr owns the ports and the pure mapping; each library owns its mirror and its adapters.** The libraries' cores never import evalr; only the extras that mirror or evaluate do.

- **One mapping, built on `verdict_fields`.** `score_configs(type, type_name=)` gives each field's `ScoreConfig`: its name, data type, description, bounds and categories. `score_values(type, value, type_name=)` pairs each field of a validated value, a model's fields or its JSON, with its config and score value. `scores(verdict)` is built on `score_values`. A library passes its registered feedback name as `type_name`. Where the copies disagreed, the libraries' behaviour wins, since it is what their users' Langfuse projects already hold:
  - A field of a type that cannot be judged is skipped, not refused, since a feedback type may have one.
  - A config's bounds are kept as declared: `gt=0` is a minimum of 0, even for an `int`. `VerdictField` keeps its inclusive bounds, which evaluators and metrics use.
  - A category or text is cut at `MAX_TEXT` (500 characters), and `None`, `""` or a missing field gives no score.
- **One `Score`: evalr's, widened.** It gains `session_id`, `timestamp` (with a time zone) and `source` (where the score came from, such as the tenant and person that gave feedback). `evaluator` and `version` become optional, since people's feedback has neither. A yes or no stays a bool, which sinks send as 1 or 0. `metadata` is the source, then the evaluator, its version and the confidence.
- **One `ScoreSink`: evalr's `record(scores)`.** The libraries' `send(score)` goes; a mirror records a piece of feedback's scores at once.
- **`ScoreConfig` and `ScoreConfigStore` move as they are**, except that a config's `feedback_type` is named `type_name`, as `scores` names it. `sync_score_configs(store, configs)` creates the configs whose names a store lacks and never changes one it has. The libraries keep their own `sync_score_configs(store, types=None)`, which syncs every registered feedback type, on top of it.
- **The rest of the port's obligations come with it:** `InMemoryScoreConfigStore`, and a contract suite, `check_score_config_store`. `check_score_sink` also checks a score on a session. `LangfuseScoreSink` records a score's session and timestamp, and refuses only a score with neither a trace nor a session. `OtelEventSink` sets `session.id` and takes the event's time from the timestamp.
- **A fixture pins the mapping.** `tests/core/score_configs.json` holds the configs and score values the libraries' copies gave for types declared in every way their feedback types are, generated from those copies. evalr's mapping must reproduce it. Differentially, the two agree on over a thousand generated declarations. They differ only on three unusual ones, where evalr's reading wins:
  - A `Literal` of `Enum` members has the members' values as its categories (`"a"`), matching the values sent; the copies gave `str(member)` (`"C.A"`), which no score matched.
  - A bound that is neither an `int` nor a `float`, such as a `Decimal`, is ignored, as `verdict_fields` ignores it.
  - An `Interval` with both `gt` and `ge` takes `ge`.

The table of ports in ADR-0006 gains a row:

| Port | What it does | Adapters |
|---|---|---|
| `ScoreConfigStore` | Keeps score configs by name, so a backend knows each score's type, range and choices | in-memory (`evalr.memory`); the libraries' `[langfuse]` extras |

`ScoreSink` records verdicts' and feedback's scores, and the libraries' `[langfuse]` extras adapt it too.

## Options considered

### Option A: evalr owns the ports and the mapping; the libraries own the mirrors and adapters (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one mapping, and a mirror per library |
| Coupling | The libraries' extras depend on evalr's core; evalr imports neither library |
| Drift | None: one copy, pinned by a fixture |

**Pros:** people's and evaluators' scores match by construction; a new backend implements two small ports once, for all three projects, checked by one contract suite.
**Cons:** the libraries' `[langfuse]` extras gain a dependency, pinned by git revision until evalr is published; a mapping change reaches them only when they move the pin.

### Option B: Keep three copies, each tested against a shared fixture

| Dimension | Assessment |
|---|---|
| Complexity | Low now, rising with every change made three times |
| Coupling | None |
| Drift | Caught by the tests, if each copy's fixture is kept in step |

**Pros:** no new dependency.
**Cons:** the fixture must itself be copied; the ports stay three pairs of protocols that an adapter can only implement for one project.

### Option C: evalr also owns the mirrors, or the Langfuse adapters of the libraries' ports

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Coupling | High: a mirror reads a workspace's log and knows its targets (turns, runs, firings, chains) |
| Drift | None |

**Pros:** less code in the libraries.
**Cons:** evalr would have to know each library's log and targets, which ADR-0001 and ADR-0006 rule out. The Langfuse adapters are small, and keeping them beside their mirrors keeps each library's Langfuse wiring in one place.

### Option D: Two score types in evalr, one for verdicts and one for feedback

| Dimension | Assessment |
|---|---|
| Complexity | Medium: two sinks for every backend |
| Coupling | As option A |
| Drift | Between the two types' mappings |

**Pros:** evalr's `Score` is unchanged.
**Cons:** a backend needs two sinks, and a mirror of evaluators' verdicts given as feedback (artifactr's `EvaluatorActor`) would record through the other.

## Trade-off analysis

The mapping is pure and small, so the cost of owning it in one place is a dependency, not a design. Keeping the libraries' behaviour where the copies disagreed means no user's Langfuse project changes: configs are created once per name and never updated, so a change to a definition would leave projects with configs from before and after it. Widening evalr's `Score` changes evalr's API only by adding optional fields and relaxing two required ones, and a text cut at 500 characters matches what the libraries have always sent to Langfuse.

## Consequences

- Easier: a feedback type and a verdict type score the same way, and a mismatch between people's scores and an evaluator's cannot arise from the mapping.
- Easier: a new score backend is a `ScoreSink` and a `ScoreConfigStore`, usable by evalr's online evaluation and by both libraries' mirrors.
- Harder: `scores(verdict)` now drops an empty text field and cuts a long one, where it kept both; an explanation longer than 500 characters in an OpenTelemetry event is cut too.
- Harder: a change to the mapping is a change to three projects' behaviour, and needs the fixture updated deliberately.
- Revisit: a Langfuse `ScoreConfigStore` in `evalr.langfuse`, if evalr's own users want configs for verdict types that are not a library's feedback type.

## Action items

1. [x] evalr: `score_configs`, `score_values`, the wider `Score`, `ScoreConfigStore`, `sync_score_configs`, the in-memory store, the contract suites and the fixture.
2. [ ] artifactr: depend on evalr in the `[langfuse]` extra, pin the revision, and replace `artifactr.scores`' mapping and ports with evalr's.
3. [ ] reflexr: the same for `reflexr.scores`.
