# ADR-0084: `ask_user` asks questions with options, and takes answers per question

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Amends:** [ADR-0010](0010-pausing-with-deferred-tools.md), whose `ask_user` took a question and a few suggested answers and was answered with any JSON; and [lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md), whose non-goal kept `ask_user` "for a plain question"

## Context

`ask_user(question, choices=None)` paused a run until someone answered, and the answer was whatever the client sent, a string in practice: portalr drew one text field, and a message posted in a paused thread answered with its text. RFC-0005 named the cost: an agent that needs a date, a severity and three checkboxes asks three times and parses free text each time. A form (`ask_form`) is the answer for a schema; most questions an agent asks are smaller: one choice among a few it can name, where it knows which it would pick.

The owner asked for `ask_user` to work as Claude Code's AskUserQuestion does: one to four questions at once, each with a short header, two to four options with a label and what each means, single or several choices, the agent's recommendation first, and, where the agent allows it, an answer in the person's own words. Answers come back structured, per question.

Nothing outside lattice depends on the old form. The libraries are pre-release; `ask_user` is called by stackr's template and docplan's agent, and answered by portalr's chat and docplan's CLI, all in this repository.

## Decision

- **`ask_user(questions)`** takes one to four `Question`s: `question`, `header` (at most 16 characters), `options` (two to four `Option`s, each a `label`, unique in its question, a `description`, and `recommended`), `multiple` and `other`. Its arguments are its `run_paused` request's `args`, as before. The shapes are `artifactr.core.questions`, and the protocol's schema carries them as `ask_user`, so clients generate their types.
- **Recommended options come first,** however the agent ordered them: `Question` sorts them, stably, and portalr shows them so with a badge.
- **An answer is one of two shapes,** the schema's `ask_user_answer`:
  - `{"answers": [{"selected": [...], "other": ...}, ...]}`, one per question, in order. A single choice has exactly one answer: a label, or the person's own words where the question offers `other`. Several choices have at least one. Labels are the question's own, each chosen once.
  - `{"reply": "..."}`: a message posted in the thread while the questions were open, in its words, which answers them all instead of choosing.
- **Core holds an answer to the questions as it is committed.** `answer_deferred` to an `ask_user` request is refused as `validation_failed`, with where (`["answers", n]`) and why, the same from the WebSocket and REST, and from the runner. `ask_form`'s answers stay `artifactr.ui`'s checks' ([ADR-0075](0075-forms-refused-at-the-boundary-through-the-checks.md)); core knows `ask_user`, its own tool, by name, as the runner already knows `ask_form`.
- **A message still answers questions,** as `{"reply": text}` ([ADR-0064](0064-asking-for-a-threads-next-turn.md)'s reply, unchanged otherwise). A person can always answer in words, in the composer, whatever the agent offered.
- **The agent is told each question beside its answer:** `ask_user` returns `[{"question", "selected", "other"?}, ...]`, or `{"reply": ...}`. The log keeps the answer as it was sent; the runner builds what the model reads as the run resumes.
- **The old string form doesn't keep working: a clean migration.** A string answer is refused. A request recorded before this change, whose `args` hold `question` and `choices`, is answered only by a reply: a message, or `{"reply": ...}`, so a run paused on one isn't stranded, and is answered as before, in words.

## Options considered

| Option | For | Against |
|---|---|---|
| **Structured questions, answered per question or by a reply, held by core (chosen)** | One contract on every surface; the model gets labels it offered, not prose to parse; a message still answers | Core knows its own tool's name; every client that answered with a string changes |
| Keep the string form beside the new one | Old clients keep working | Two contracts to test and describe, for clients that are all in this repository |
| A message no longer answers questions; only the card does | One answer shape | A person can't just reply, and a CLI or MCP client would need the card's shape to answer at all |
| Hold answers in `artifactr.ui`'s checks | Core unchanged | An application without the forms extra would accept any answer to `ask_user` |
| `ask_form` for every question | One tool | A JSON Schema for "Monday or Friday?"; no recommendation; models fill it worse |

## Consequences

- Easier: an agent asks what it needs in one pause, says which option it would choose, and reads back the labels it offered.
- Easier: a client renders a question without guessing: a radio or checkbox group, a header, a badge, and a text field only where `other` is offered.
- Harder: a client that answered with a string sends `{"answers": ...}` or `{"reply": ...}`. portalr, docplan and the template's scripted tests are changed here.
- Revisit: four questions and four options are Claude Code's limits; raise them if agents need more and people still answer them.
