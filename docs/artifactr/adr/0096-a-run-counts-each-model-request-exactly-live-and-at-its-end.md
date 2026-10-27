# ADR-0096: A run counts each model request exactly, live and at its end

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0095](0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md), whose `RunUsage` gains the model, the reasoning tokens and the steps it left to a later record; [ADR-0007](0007-caller-owned-live-output.md) with one more live frame

## Context

The owner asked to "see token counts for input, output, cache as the content streams". portalr's strip ([portalr ADR-0083](../../portalr/adr/0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md)) shows an estimate, characters over four, because artifactr sent nothing better while a run ran, and recorded only a run's sums at its end: not which model answered, which a gateway decides, nor what each request of a long run cost, nor what a reasoning model spent thinking.

pydantic-ai has the provider's counts for each request as its response ends (`ModelResponse.usage`, a `RequestUsage`, and `ModelResponse.model_name`, the model the response names). Verified against pydantic-ai 2.55's source: through `OpenAIChatModel`, as artifactr reaches LiteLLM, `prompt_tokens_details.cached_tokens` becomes `cache_read_tokens`; `completion_tokens_details` is copied into `details`, so the reasoning is `details["reasoning_tokens"]`, as pydantic-ai has no field for it; and any other top-level integer of the usage lands in `details` too, which is where LiteLLM's `cache_creation_input_tokens`, Anthropic's cache write, ends up, as pydantic-ai lifts only `prompt_tokens_details.cache_write_tokens` into `cache_write_tokens`. A test drives the run through a fake proxy that reports all three, as LiteLLM does for Anthropic.

## Decision

- **`RunUsage` gains `reasoning_tokens`, `model` and `steps`.** `reasoning_tokens` is of the output tokens, 0 where the provider doesn't say; `model` is the model that answered the run's last request; `steps` is a `StepUsage` per model request, oldest first: `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens` and `duration_ms`, from the request's sending to its response's end. Every field has a default, so an event recorded earlier reads as 0, `None` or no steps, and the protocol stays `artifactr.v1`. The cache write is `cache_write_tokens`, or, where that is 0, the usage's `cache_creation_input_tokens` detail.
- **The capability counts in `wrap_model_request`.** `ArtifactWorkspace` times the request, maps its response to a `StepUsage`, keeps it in the run segment's `Session.steps`, and emits it as a `StepUsed` capability event, which `forward_live` turns into a `usage` live frame. A run that completes, pauses, is stopped or fails records its steps so far with its sums in `run_ended` or `run_paused`; the sums are pydantic-ai's run usage, as before.
- **A `usage` live frame per model request.** `UsageUpdate{step, usage, total, exact}`: the request's index among the segment's, from 0; what it used; the segment's total so far, the steps summed, its own `steps` left out; and `exact`, true, as the counts are the provider's. The live total sums the steps rather than reading pydantic-ai's run usage, because pydantic-ai adds a streamed response's tokens before it counts the request, so mid-step its count is neither one thing nor the other; once the step is done they agree, and the run's end records pydantic-ai's.
- **A total, never an increment.** A client keeps the total with the most `requests` and replaces what it has with it, so a frame replayed on reconnect, or a late one, counts nothing twice; `run_ended`'s `usage` replaces it at the end.
- **Never shed.** The outbox drops only `thinking_delta` ([ADR-0095](0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md)); a `usage` frame waits for room as other live frames do. `FanoutChannel` keeps each run's latest `usage` frame beside its buffer, and sends it to a watcher that attaches after it left the buffer, after the buffered frames, as a total says the same whenever it comes.

## Options considered

### Option A: Count in `wrap_model_request`, send through the event stream (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one hook, one capability event, one translation in `to_live` |
| Exactness | The provider's own counts, per request, as the response ends |
| Coupling | The capability needs no channel: the runner's `forward_live` carries the frame, as it carries drafts |

### Option B: Read the counts from the stream in `forward_live`

| Dimension | Assessment |
|---|---|
| Complexity | Medium: no stream event carries a response's final usage |
| Exactness | Only what the stream says as it ends, with no model and no timing |

Rejected: the stream doesn't say it.

### Option C: Send only the run's total, from pydantic-ai's run usage

Rejected: mid-step it counts a streamed response's tokens but not its request, and it says nothing of which request cost what.

## Consequences

**Positive:**
- A client shows the provider's numbers within a request of a run's start, and the model that answered.
- A stopped or failed run's end says what each request cost, and which model answered it.

**Negative:**
- `run_ended` grows by a step per model request; a run of a hundred requests carries a hundred small objects.
- The live total and the recorded one can differ where pydantic-ai counts what no step saw, such as a `FallbackModel`'s rejected attempts, which artifactr doesn't use.

**Risks:**
- A gateway that reports a cache write some other way counts it as 0 until artifactr reads it; Anthropic's through LiteLLM is read from the detail above, verified against pydantic-ai's source and a fake proxy, not a real call.

## Action items

1. [x] `StepUsage`, the new `RunUsage` fields, `UsageUpdate` and `StepUsed`; the schemas and the client's types regenerated
2. [x] portalr's strip shows the exact counts, the cache and reasoning where any, and the model ([portalr ADR-0083](../../portalr/adr/0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md))
3. [ ] Cache awareness reads the cache fields and the answering model (the streaming design's phase E)
