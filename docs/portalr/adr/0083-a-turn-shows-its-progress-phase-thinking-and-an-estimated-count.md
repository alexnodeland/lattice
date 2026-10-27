# ADR-0083: A turn shows its progress: phase, thinking, and an estimated count

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0053](0053-the-chats-questions-tool-calls-sides-failures-and-streaming.md) (what streams, and the three dots before it; a call's arguments and result, and what Copy copies), [ADR-0080](0080-ink-on-paper-the-products-visual-language.md) (the strip over a turn)

## Context

The owner watched a turn for five minutes and saw three dots. artifactr streams every part the model produces, text, thinking and a tool call's arguments as they are generated (artifactr ADR-0007, `docs/artifactr/guides/live-output.md`), but `client`'s store kept only `text_delta`, and the chat drew dots until the first word of text. A reasoning model, or a tool call whose arguments run to kilobytes, is minutes of apparent silence: "It's also been working for 5 mins but I see no progress. I should be able to switch the model, see token counts for input, output, cache as the content streams. I should see thinking if available and stream token by token text where possible. Sitting and waiting for 5 mins is unacceptable."

The store had three further faults. Text accumulated across every text part of a turn, so what the model wrote before a tool call ran into the reply. Each delta told every listener at once, so a stream of two hundred deltas a second was two hundred renders of the thread. And a run's end wiped its text, so a turn that failed, or was stopped, took what it had written with it. On a reconnect, the server replays up to 1,024 of a running run's frames (`FanoutChannel`), and the store would have appended them to what it already had.

This record is the chat's half of the streaming design: what the UI shows from the frames that exist today. Exact token counts, the model that answered, and cache awareness need new fields from artifactr and are later phases; the strip is built so they plug in.

## Decision

- **The store keeps what a run is doing.** A `Run` has `live`: its `phase` (`starting`, `thinking`, `tool` or `writing`), the tool being prepared or run, the characters of its arguments so far, the model's `thinking`, the milliseconds spent in thinking parts that have ended, every character the model has produced this turn, and when the phase began and the last frame came, by the browser's clock. `part_started` sets the phase; `tool_called` says the tool runs, `tool_returned` and `run_paused` that the model is waited on again; a resumed run starts afresh.
- **A new response's text replaces the old.** pydantic-ai numbers the parts of each model response from 0. A text part whose index is at or below the last text part's begins a new response, and the reply is that response's text: what the model wrote before its tool call isn't the reply, as the posted message, which is `result.output`, won't hold it. Within one response, a second text part goes on from the first.
- **The listeners hear once per frame.** The store applies each live frame as it arrives and tells its listeners on the next animation frame, once for however many frames came in between; any other change tells them at once, which also delivers what was put off. A tab that is hidden draws nothing until it is shown.
- **A reconnect starts live output over.** `Protocol` gains `welcome(state)`, which the store calls as a connection is welcomed without a reset, before the replay: artifactr's resets every running run's text and `live`, so the frames the server sends again show nothing twice. A frame buffer that overflowed loses its oldest frames, so the head of a long text may be missing after a reconnect: an `offset` per delta, or a snapshot on watch, is artifactr's to add (phase B).
- **What streamed outlives a failure.** `run_ended` keeps the text and thinking of a run that failed or was stopped; `message_posted` clears both, as the posted message is the reply, and a completed run has posted it. `threadLog` puts a `partial` entry before a failed turn's notice, at the same place, and `Streaming` draws it quietly, in the muted colour, with "Stopped here." under a stopped turn.
- **The strip says what the turn is doing.** Beside its status, a line reads "Waiting on the model", "Thinking", "Preparing `create_app` call, 12 KB", "Running `create_app`" or "Writing the reply"; after twenty seconds without a frame, ", 40 s since the last output" joins it, counting. The clock stays. Stop stays while the run works, where `artifactr:stop_run` allows.
- **Thinking is folded under the words.** Where the model shows its thinking, `Streaming` has a disclosure above the bubble, "Thinking…" while it thinks and "Thought for 12 s" after, closed by default, holding the thinking as preformatted text and the line "Thinking isn't kept: it goes when the page does." Everyone who can see the thread sees it (the owner's decision); it is never stored, never sent anywhere, and goes with the run's reply.
- **A token count, estimated until exact.** Under the strip, "Tokens: about 1,000 in, about 101 out, estimated": the characters of the thread's messages before the turn over four, and the characters the model produced over four. `RunStrip` takes an optional `usage` (`input`, `output`, `cacheRead`, `cacheWrite`, `reasoning`), and once a run says its counts exactly the line shows them without the word "estimated": phase C's `UsageUpdate` fills it. The estimate is a rough guide, said to be one, never a tokenizer.
- **What is announced.** The streaming item is `aria-live="off"` inside the log, so nothing of what grows, words, thinking or the disclosure's label, is announced; the posted message is. The strip has one `role="status"`, kept through the add-on's loading, which says how the run goes and what it does, "Working: Writing the reply", on a change and at most every three seconds, with ", nothing for a while" once the idle count begins; the clock, the idle count and the token line are never live. The disclosure is a button with `aria-expanded`; the focus never moves by itself; the three dots stay still under reduced motion, as before.
- **A call's parts, formatted.** The owner read a `create_app` call's arguments on a phone: one line of JSON with a page of HTML escaped inside it. Open, a call's Arguments and Result each have a toggle, Formatted or Raw, two buttons pressed as chosen, where the value parses as JSON; a value that doesn't has none. Formatted lays the JSON out with its keys quiet before their values, nested values indented, and a string that holds lines, or more than a line's worth, as a block of its own under its key, wrapped to the box: as code, in the kit's `CodeBlock` with its language, Wrap and Copy, where its key or its first characters say it is code (`html`, `css`, `script`, `source`, a `<!doctype`), and as plain preformatted text otherwise. Nothing of a value is run or parsed as HTML. Raw is the JSON indented, as before. A value the run cut short is closed where it stopped, or cut back to its last boundary, so what parses is shown, with "Formatted from what parses of it."; one past 200,000 characters, or that parses no way, is shown raw with a note. Copy copies the value as the run recorded it, in either view, which it didn't before (it copied the indented JSON): the recorded text is the one that is exact. The choice is one for every call, kept in the browser as `portalr:tool-call-view` ("raw", or nothing), and every open call of the tab follows it. It is the `json-view` add-on, loaded as a call is first opened; its storage is its own few lines rather than `stored-setting`, whose chunk the total budget hasn't room for, and it highlights nothing, since the highlighter's chunk would be shared with the chat for the same cost.
- **Bytes.** The app's initial budget had 1,279 gzipped bytes to spare. The store's additions and the chat's own (`aria-live`, the disclosure, the kept partial text) fit; the phase's wording, the throttled status and the token line are the `streaming` add-on (`ui/src/on-demand/streaming.tsx`), loaded as the first run streams, with a budget of its own, 1,100 bytes. The add-on imports nothing the chat doesn't hold already: an import of `Disclosure` from it made the bundler split Base UI's collapsible into chunks shared with the chat, which cost 1.7 KB of the initial for nothing. The disclosure is in `chat.tsx` for that reason. Until the add-on has loaded, the status says the run's status alone.

## Options considered

| Option | For | Against |
|---|---|---|
| **The phase from the existing frames (chosen)** | No wire change; lands now | A tool's arguments are counted, not read; no exact tokens |
| A phase event from artifactr | One source of truth | A new event for what the frames already say |
| **Coalesce in the store, per animation frame (chosen)** | One render per frame for the whole thread | A `later` path in `Stream` |
| Throttle in `Streaming` alone | Touches no shared code | The thread still renders per delta |
| **A text part at or below the last index starts over (chosen)** | Keeps a response's several text parts; drops a tool call's preface | Relies on pydantic-ai numbering from 0 per response |
| Reset on every text part | Simplest | Drops a response's earlier text parts |
| **Reset on welcome (chosen)** | Replay idempotent today | A buffer that overflowed loses the head |
| De-duplicate by offset | Exact | Needs an `offset` the frames don't carry yet (phase B) |
| **Thinking as preformatted text (chosen)** | Cheap; nothing to parse mid-stream | No Markdown in thinking |
| Thinking through `Markdown` | Headings and lists where a model writes them | Another streaming parser per delta |
| **Phase wording in an add-on (chosen)** | Fits the budget; one chunk, cached | The first turn's phase line waits a round trip |
| Raise the initial budget | Everything in the first load | The owner's ceiling, and a precedent |

## Consequences

- Easier: a reader sees that the model is thinking, what call it is preparing and how much of it, and when nothing has come for a while; a stopped or failed turn keeps what it wrote; a reconnect shows nothing twice.
- Harder: `apply` reads the clock for a run's phase, where it was pure; tests pass `now` to `applyLive`. The estimate counts characters of messages alone: tool results, system prompts and attachments aren't in it, so it is low for a turn with many calls.
- Harder: the thinking is held in memory for the run's life, and a model that thinks for pages holds pages; it goes with the reply.
- Deferred to artifactr (phase B): an `offset` per delta or a snapshot on watch, usage on a stopped or failed `run_ended`, an idle watchdog. To phase C: `UsageUpdate` into `usage`. To phases D and E: the model picker and the cache hint, beside the token line.
- The streaming text's `aria-live="off"` and the strip's one status are held by tests: mutating the text adds no live region, and the status excludes the clock.

## Action items

1. [x] `client`: `Live` on `Run`, `applyLive`, `welcome`, kept partial text, the store's `later` telling.
2. [x] `ui`: `Streaming`'s disclosure and `ended`, `RunStrip`'s status, `Said` and `Doing` in the `streaming` add-on, `Usage`; a call's Formatted and Raw in the `json-view` add-on.
3. [x] `app`: `partial` entries in `threadLog`; the thread's history for the estimate.
4. [ ] Phase C: fill `usage` from `UsageUpdate` and `RunEnded.usage`.
