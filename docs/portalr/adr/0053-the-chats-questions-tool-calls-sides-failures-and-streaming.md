# ADR-0053: The chat's questions, tool calls, sides, failures and streaming

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Amends:** [ADR-0015](0015-the-chat-components-and-streamdown.md)'s tool-call row and question card, and [ADR-0016](0016-the-threads-area.md)'s composer, which kept its text until the post was done

## Context

The owner used the chat against a generated application and asked for five things:

- **Questions as options.** `ask_user` now asks one to four questions with options ([artifactr ADR-0083](../../artifactr/adr/0083-ask-user-asks-questions-with-options.md)); the chat drew a question as one text field.
- **Tool calls that can be read.** A call was a row with a name and a status; what it was asked, what it returned, and why it failed weren't shown, and the rows went once the run ended.
- **Sides.** Every message sat at the start of the line, the reader's as the agent's.
- **Failures that say why.** A run that ended `failed` left the thread: no status, no reason, nothing to retry. In the owner's case the model had filled `draft_rule`'s arguments wrongly until it ran out of retries, and the thread said nothing.
- **Latency that feels short.** A message showed only once the server had it, and nothing showed between it and the agent's first words.

The store dropped what each needs: a call's arguments and result, a run's end, error and reason, and what a run had asked once it resumed.

## Decision

- **The store keeps them.** A `Tool` has its `args` and `result`, as the run recorded them (artifactr's summaries, 2,000 characters by default), and the `seq` it was called at. A `Run` has `ended`, `error` and `reason`, and `questions`: each `ask_user` request it paused on, where, and its answer and who gave it, for the run's life.
- **The thread is one log.** `threadLog` puts a thread's messages, its runs' calls (a run's calls in a row as one group), its questions, and its failed turns in the log's order. A call still open once its run paused or ended, as a form's or a question's is, isn't shown as a call: its card is.
- **`Questions` draws `ask_user`.** Each question is a radio group, or a checkbox group where it takes several, named by its header, a chip, and its words. Each option is a row that is its own radio or checkbox, so the whole row chooses it and the arrow keys move between them: named by its label and, where the agent recommends it, its "Recommended" badge, and described by what it means. Recommended options come first. Where the agent offers it, "Other" opens a field for the reader's own words, which takes the focus. "Answer" sends every question's answer at once, or says under a question what it still needs and moves the focus to it. Answered, the card stays where it was asked and says what was chosen, or the reply that answered it, and by whom. The newest request takes the focus as it appears, a frame later, once Base UI's groups have their options: focused before, a radio group's arrow keys don't move.
- **A call is a `<details>`.** Closed, its summary line has the tool's name, a status in a shape and a word (Running, Done, Failed, Refused), and a line of its arguments, or of why it failed or was refused, so an error shows without opening it. Open, it has its arguments and its result, JSON indented, each capped at 16rem and scrolled, each with a copy button. The native element opens with Enter and Space, and is announced as expanded or collapsed, with no script.
- **The reader's messages are at the end of the line,** in a bubble washed in the working colour; everyone else's, the agent's and other people's, are at its start, in a surface bubble. The sides are `align-self` and logical corners, so a page written right to left mirrors them. A message keeps its name, the author's.
- **A failed turn says why,** in the thread, where it ended: "The assistant couldn't finish." and a sentence for its reason (the model ran out of tries on a tool, answered in a way the turn couldn't use, the turn was given up, a guardrail stopped it), or that something went wrong. The run's own error, redacted on the server ([artifactr ADR-0084](../../artifactr/adr/0084-what-a-run-records-of-its-calls-and-who-reads-it.md)), is under "Details" only for the person the turn acted for. The thread's latest turn, if it failed and the reader started it, has "Try again", announced as an alert; one further up is a note.
- **"Try again" posts the message that started the turn again,** the first that its `run_started` names, under an id derived from the run (`msg_again_<run>`). The server takes a message id once ([artifactr ADR-0045](../../artifactr/adr/0045-a-message-id-is-used-once.md)), so a second click, a retry from another tab, or a resend after a lost answer is the same message, not another; the button waits while its post is in flight, and goes once the thread has it.
- **Who sees a call:** everyone who may read the thread, as for every event in it, but for a call that names an artifact the reader may not see, which is left out with it (artifactr ADR-0084).
- **What streams sits where its message will.** `Streaming` has the bubble, and the row of actions' height, that the posted message has, so nothing moves when one replaces the other. Before the first words, it is three dots that pulse in turn, "Thinking" to a screen reader, and still where motion is reduced.
- **A message shows as it is sent.** The app posts it under an id it chooses, and shows it, "Sending…", until the thread has that id. Refused, it goes, and the composer puts its words back, unless the reader has written something since. One whose answer never came, which the server may have, stays, saying it may not have been sent, with "Send again" under the same id, which the server takes once. The composer clears as it sends.

## Options considered

| Option | For | Against |
|---|---|---|
| **Each option row is its own radio or checkbox (chosen)** | The whole row chooses; arrow keys work; one name and one description each | Base UI's controls hold the row's content, not the kit's `Checkbox` |
| A `<label>` around the kit's controls | Reuses `Checkbox` | Base UI's radio group stops moving by arrow keys inside a label |
| **`<details>` for a call (chosen)** | Keyboard, state and announcement for free | Its marker is the browser's, hidden and drawn as a chevron |
| A disclosure button and a region | Full control | Script and state for what the element does |
| **Retry re-posts the reader's last message (chosen)** | No new command; the turn is asked as any is | A turn that failed after a resume starts over |
| A command to retry a run | Resumes where it failed | A new command in artifactr's protocol for one button |
| **Show the message at once, under the app's id (chosen)** | No wait; no flicker when the event comes, since the id matches | A refused message appears, then goes |
| React's `useOptimistic` | Built in | It ends with the send, before the event, so the message would blink out and back |

## Consequences

- Easier: a reader sees what the agent did, and why it stopped, without leaving the thread, and answers its questions in a click each.
- Harder: a thread with many calls is longer; each is one line until opened.
- Harder: "Try again" starts the turn over from its first message. What the failed turn did before it failed, such as an artifact it created or a proposal it made, stands, and the new turn may do it again: the agent is told what changed, but a tool with effects outside artifactr has no such guard. A turn that paused and resumed asks its first questions again.
- Deferred: a retry command in artifactr that resumes a failed run where it stopped, with what it already did in its history. It is a change to the runner's claims and the protocol, for one button, and is left until starting over proves wrong.
