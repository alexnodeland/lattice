# Workflow measures

Some questions are about a whole workflow rather than one reply: did the session achieve what the person asked? Did the person give up waiting? How much of what the agent wrote did people rewrite? `evalr.measures` defines these end-to-end measures generically, in terms any application's log can be put in, and each library's `[evals]` extra supplies the data.

| Measure | Verdict | How |
|---|---|---|
| [Task completion](#task-completion) | `TaskCompletion` | Judged: any evaluator reading a `Transcript` |
| [Drop-off](#drop-off) | `DropOff` | Computed from a `Session`'s activity |
| [Rewrites](#rewrites) | `Rewrites` | Computed from an artifact's `History` |

Each is a verdict type, so its results are verdicts: they are scored, run in [experiments](experiments.md) and [online](online.md), and summarized like any other.

## The inputs

The measures read three inputs, which say nothing about any one library:

| Input | Holds | From artifactr | From reflexr |
|---|---|---|---|
| `Session` | A timeline of `Activity`: when, who (`person`, `agent` or `system`), what (`message`, `proposal`, `resolution`, or anything else), and a `ref` pairing a proposal with its resolution | A thread | A causal chain |
| `History` | An artifact's `Revision`s: when, who, and its whole text | An artifact | A report people edit |
| `Transcript` | The request, the `Turn`s of the conversation, and the result | A thread and its artifacts | A chain's events and reports |

An application without a library's extra builds them from its own records.

## Task completion

Whether a session achieved what the person asked for is a judgement, so task completion is a verdict type for any evaluator:

```python
import dspy

from evalr.dspy import DspyJudge
from evalr.measures import TaskCompletion, Transcript, Turn, completion_rate

completion = DspyJudge(TaskCompletion, inputs=Transcript, lm=dspy.LM("openai/gpt-5-mini"))

transcript = Transcript(
    request="Draft the launch brief and list its risks",
    turns=[
        Turn(role="person", text="Draft the launch brief and list its risks"),
        Turn(role="agent", text="Here is the brief, with a risks section."),
    ],
    result="# Launch\n\nWe ship on Monday.\n\n## Risks\n\n- Legal review may slip.",
)
verdict = await completion.evaluate(transcript)
print(completion_rate([verdict]))
```

`TaskCompletion` has `completed` (the request was achieved), `quality` (how well, from 1 to 5) and an optional `reason`. A [decision evaluator](decision-evaluators.md) can judge it too, since its only text field is optional, and people can give it as feedback, so the judge can be [trained](dspy-judges.md#training-with-gepa) and [measured](metrics.md) like any other. `completion_rate(verdicts)` is the share judged completed, or `None` for none.

## Drop-off

A session drops off when the agent was left waiting on a person who never came back. `measure_drop_off` decides it from the session's activity, given how long a person has to come back and when the log was read:

```python
from datetime import UTC, datetime, timedelta

from evalr.measures import Activity, Session, measure_drop_off

start = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
session = Session(
    id="thr_1",
    activities=[
        Activity(at=start, role="person"),
        Activity(at=start + timedelta(minutes=1), role="agent"),
        Activity(at=start + timedelta(minutes=2), role="agent", kind="proposal", ref="prop_1"),
    ],
)
print(measure_drop_off(session, window=timedelta(hours=1), now=start + timedelta(hours=3)))
```

```text
outcome='dropped' cause='unresolved_proposal'
```

- **Dropped, `unresolved_proposal`:** a proposal was left unresolved for longer than the window.
- **Dropped, `no_reply`:** no person acted within the window after the agent's last activity.
- **Continued:** a person acted within the window after the agent's last activity, or the agent never acted.
- **Pending:** too soon to tell: the window since the agent's last activity, or since an unresolved proposal, has not passed yet.

`drop_off_rate(verdicts)` is the share of decided sessions that dropped off: pending ones are left out.

## Rewrites

When a person substantially rewrites what the agent wrote, the agent's draft missed. `measure_rewrites` counts the agent's revisions of an artifact that a person rewrote soon after:

```python
from evalr.measures import History, Revision, measure_rewrites

history = History(
    id="brief",
    revisions=[
        Revision(at=start, role="agent", text="We ship the new billing page on Friday."),
        Revision(
            at=start + timedelta(minutes=10),
            role="person",
            text="We ship the billing page on Monday, once legal has signed off.",
        ),
        Revision(
            at=start + timedelta(hours=1),
            role="agent",
            text="We ship the billing page on Monday, once legal has signed off. Risks: none.",
        ),
    ],
)
print(measure_rewrites(history, window=timedelta(hours=1)))
```

```text
agent_revisions=2 rewritten=1 rate=0.5
```

A person's revision rewrites the agent's when it comes within the window after it, before the agent writes again, and changes at least `threshold` of its text (0.2 by default): one minus `difflib`'s similarity ratio. Of several such revisions, the last counts. `rewrite_rate(verdicts)` pools the revisions of many artifacts: rewritten over all the agent's revisions.

## Measures as evaluators

`drop_off_evaluator(window=, now=)` and `rewrite_evaluator(window=, threshold=)` wrap the computed measures as [function evaluators](function-evaluators.md), versioned by their settings (`drop-off` at `1:3600s`, `rewrites` at `1:3600s:0.2`), so a change of window is a new version:

```python
from evalr.measures import drop_off_evaluator, drop_off_rate

drop_off = drop_off_evaluator(window=timedelta(hours=1), now=start + timedelta(hours=3))
verdicts = [await drop_off.evaluate(session)]
print(drop_off_rate(verdicts))
```

They run in [experiments](experiments.md) and [online](online.md) like any evaluator, and their verdicts become scores named `drop_off.outcome`, `rewrites.rate` and so on.

reflexr's extra adds measures of its own over rules and chains, computed from its log: each rule's dead-letter, retry and operator-intervention rates, and each chain's time to resolution.
