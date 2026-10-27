# ADR-0096: A run counts each model request exactly, live and at its end

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0095](0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md), whose `RunUsage` gains the model, the reasoning tokens and the steps it left to a later record; [ADR-0007](0007-caller-owned-live-output.md) with one more live frame

## Context

The owner asked to "see token counts for input, output, cache as the content streams". portalr's strip ([portalr ADR-0083](../../portalr/adr/0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md)) shows an estimate, characters over four, because artifactr sent nothing better while a run ran, and recorded only a run's sums at its end: not which model answered, which a gateway decides, nor what each request of a long run cost, nor what a reasoning model spent thinking.

pydantic-ai has the provider's counts for each request as its response ends (`ModelResponse.usage`, a `RequestUsage`, and `ModelResponse.model_name`, the model the response names). Verified against pydantic-ai 2.55's source: through `OpenAIChatModel`, as artifactr reaches LiteLLM, `prompt_tokens_details.cached_tokens` becomes `cache_read_tokens`; `completion_tokens_details` is copied into `details`, so the reasoning is `details["reasoning_tokens"]`, as pydantic-ai has no field for it; and any other top-level integer of the usage lands in `details` too, which is where LiteLLM's `cache_creation_input_tokens`, Anthropic's cache write, ends up, as pydantic-ai lifts only `prompt_tokens_details.cache_write_tokens` into `cache_write_tokens`. A test drives the run through a fake proxy that reports all three, as LiteLLM does for Anthropic.

## Decision

- **`RunUsage` gains `reasoning_tokens`, `model` and `steps`.** `reasoning_tokens` is of the output tokens, 0 where the provider doesn't say; `model` is the model that answered the run's last request; `steps` is a `StepUsage` per model request, oldest first: `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens` and `duration_ms`, from the request's sending to its response's end. Every field has a default, so an event recorded earlier reads as 0, `None` or no steps, and the protocol stays `artifactr.v1`. A step's cache write is its `cache_write_tokens`, or, where that is 0, its usage's `cache_creation_input_tokens` detail.
- **The steps are the source of the token sums.** Where a run has steps, `RunUsage`'s token fields are theirs, summed, so a step whose cache write was a detail and another whose was first-class add up; `requests` stays pydantic-ai's. A step is a request whose response ended. A run stopped or failed mid-request records, after its steps, one step without a model or a duration for what pydantic-ai counted that no step did, so nothing it used is dropped: so a stopped or failed run's `steps` may be one more than its `requests`, as that last step may be a request pydantic-ai has not counted yet; a request torn down before its response ended has, in pydantic-ai 2.55, counted nothing, and a test says so. A completed run has no such step: what a `FallbackModel`'s rejected attempts used, which artifactr doesn't use, isn't in it.
- **The capability counts in `wrap_model_request`.** `ArtifactWorkspace` times the request, maps its response to a `StepUsage`, keeps it in the run segment's `Session.steps`, and emits it as a `StepUsed` capability event, which `forward_live` turns into a `usage` live frame. A run that completes, pauses, is stopped or fails records its steps so far with its sums in `run_ended` or `run_paused`; the token sums are the steps', its `requests` pydantic-ai's.
- **A `usage` live frame per model request.** `UsageUpdate{step, usage, total, exact}`: the request's index among the segment's, from 0; what it used; the segment's total so far, the steps summed, its own `steps` left out; and `exact`, true, as the counts are the provider's: always true from this version, which sends no estimate, kept so a later estimate on the wire says so. A `usage` frame is no output: the client's idle count doesn't restart on it. The live total sums the steps rather than reading pydantic-ai's run usage, because pydantic-ai adds a streamed response's tokens before it counts the request, so mid-step its count is neither one thing nor the other; the run's end sums the same steps, so the last frame's total and the recorded one agree.
- **A resumed run is a new segment.** A run resumed after a pause runs under a new `Session`: its steps, `step` and the live `total` count from 0 again, and its `run_ended`'s usage covers the segment from its resumption; the pause's `run_paused` carried the segment before. A client takes the first `usage` frame after a resume whatever its `requests`, as its live state starts afresh on the resume.
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
- A completed run's sums leave out what pydantic-ai counted that no step saw, such as a `FallbackModel`'s rejected attempts, which artifactr doesn't use.

**Bytes (portalr):** the store's reducer added 70 gzipped bytes to the app's initial bundle, measured locally with `check_size.py`: 203,431 of 203,500. Everything drawn is the `streaming` add-on's, which grew from 1,061 to 1,248 bytes: the exact chips' variant of the label and its screen-reader name without "estimated", the three optional chips (cached, cache write, reasoning) as one table mapped through the same `Chip`, and the model's quiet line with its "Model:" name. To stay small the chips reuse the estimate's `Chip` and its class list rather than a second style, the optional chips are data rather than three branches, and nothing formats a number but `toLocaleString`. Its budget was raised from 1,100 to 1,300, approved by the owner on 2026-10-27; the app's initial, total and canvas ceilings are unchanged.

**Risks:**

- A gateway that reports a cache write some other way counts it as 0 until artifactr reads it; Anthropic's through LiteLLM is read from the detail above, verified against pydantic-ai's source and a fake proxy, not a real call.

## Action items

1. [x] `StepUsage`, the new `RunUsage` fields, `UsageUpdate` and `StepUsed`; the schemas and the client's types regenerated
2. [x] portalr's strip shows the exact counts, the cache and reasoning where any, and the model ([portalr ADR-0083](../../portalr/adr/0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md))
3. [ ] Cache awareness reads the cache fields and the answering model (the streaming design's phase E)
