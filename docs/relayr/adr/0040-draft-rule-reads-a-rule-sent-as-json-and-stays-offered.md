# ADR-0040: `draft_rule` reads a rule sent as JSON, and stays offered

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

## Context

In a generated application, against GLM through LiteLLM, every `draft_rule` call failed validation with `rule: Input should be an object`: the model sent the nested `Rule`, a 9 KB schema of filters and patterns, as a string of JSON, on every try, until the run failed with "Tool 'draft_rule' exceeded max retries count of 1". More retries only failed later. The owner asked whether the tool should be simpler, or only offered when relevant.

## Decision

- **A rule sent as a string of JSON is read as the object it encodes,** before validation. The schema the model is shown is unchanged, so models that send an object are unaffected. A string that isn't JSON, or nests past Python's limit, is refused as what it is.
- **`RuleDrafting(retries=3)`:** the refusal says what to change, and three tries let a model act on it.
- **`draft_rule` stays offered in every turn.** A thread gives no clean signal of when a rule is wanted: a keyword or a classifier would hide the tool from the turn that needs it, and the tool's description already says when to use it.
- **The `Rule` schema stays as reflexr defines it.** A simpler input for the model would be a second rule language to keep in step.

## Consequences

- Easier: GLM, and models that send nested objects as strings, draft rules.
- Harder: nothing; a model that sends a string of something else is refused as before.
- Revisit: offering the tool by the workspace's integrations, if rules become an integration.
