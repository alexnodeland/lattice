# Defining artifact types

An artifact is anything people and agents work on together: a document, a plan, a spec, a table of data. The library provides versioning, patches, validation, change history and agent tools; your application provides the types. This page covers how to define them and the hooks that shape how they behave. The decision behind this design is [ADR-0003](../adr/0003-artifact-types-as-pydantic-subclasses.md).

## A type is a Pydantic model

Subclass `Artifact` and declare ordinary Pydantic fields:

```python
from typing import ClassVar, Literal

from pydantic import BaseModel

from artifactr import Artifact, WritePolicy, new_id


class Task(BaseModel):
    title: str
    status: Literal["todo", "doing", "done"] = "todo"


class Plan(Artifact):  # registered as "plan"
    write_policy: ClassVar[WritePolicy] = "propose"

    goal: str = ""
    tasks: dict[str, Task] = {}

    def add_task(self, title: str) -> str:
        task_id = new_id("task")
        self.tasks[task_id] = Task(title=title)
        return task_id
```

As in any Pydantic model, fields without defaults must be given when the artifact is created. `Artifact` sets `extra="forbid"` and `validate_assignment=True`, so unknown fields and invalid assignments fail early. Methods such as `add_task` are yours: they make edits read well in application code and tools.

Prefer dictionaries keyed by id over lists for collections that change. Edits are recorded as JSON Patch, and a patch that says "set `/tasks/task_3f9c.../status`" still means the same task after someone else inserts one; "set `/tasks/2/status`" may not.

## Names and registration

Defining the class registers it, in Pydantic's `__pydantic_init_subclass__` hook. The registered name, available as `Plan.kind`, is the class name in snake case. It is stored with every artifact and sent on the wire, so choose it deliberately:

```python
from artifactr import MarkdownArtifact


class ReleaseNotes(MarkdownArtifact):  # registered as "release_notes"
    pass


class Spec(Artifact, name="product_spec"):  # an explicit name
    title: str


class Document(MarkdownArtifact, abstract=True):  # a shared base; not registered
    title: str = ""


class Memo(Document):  # registered as "memo"
    pass
```

Registering a different class under a name that is already taken raises `TypeError`; pass `name=` to choose another. `artifactr.core.artifact_types()` returns every registered type, and `get_artifact_type(kind)` looks one up.

Registration is process-wide, so a workspace does not accept every registered type by default. List the types your application accepts when you create `Workspaces`, and creating any other type is rejected, even one registered by a library you imported:

```python
from artifactr import InMemoryStorage, Workspaces

workspaces = Workspaces(InMemoryStorage(), types=[Plan, ReleaseNotes])
```

## Write policies

`write_policy` decides how an **agent's** changes to this type are applied:

| Policy | An agent's create, edit or archive |
|---|---|
| `"direct"` (the default) | is applied, and returns `Applied` |
| `"propose"` | is recorded as a proposal, and returns `Proposed` |

Write policies bind agents only: the thread's built-in agent and external agents connected over MCP. Changes by people and by the system always apply directly. A thread can also be switched into suggest mode (`SetThreadMode(thread_id=..., mode="suggest")`), which makes its agent propose every change whatever the type's policy. Anyone, person or agent, can propose explicitly with `ProposeChange`. [Workspaces, commits and the log](workspaces.md#proposals) covers how proposals are answered, and [The agent](agent.md#proposals) covers how the agent hears the outcome.

## What the agent sees

`render_for_agent()` returns the text the agent sees for an artifact: in its instructions, when it follows the artifact, and when it reads it with the `read_artifact` tool. The default is the data as indented JSON, which works but spends tokens on punctuation. A compact rendering usually helps the model more:

```python
class Plan(Artifact):
    goal: str = ""
    tasks: dict[str, Task] = {}

    def render_for_agent(self) -> str:
        lines = [f"Goal: {self.goal}"]
        lines += [
            f"- [{task.status}] {task.title} ({task_id})" for task_id, task in self.tasks.items()
        ]
        return "\n".join(lines)
```

Include the ids the agent needs to pass to your tools, as this rendering does. The capability clips each rendering in the instructions to `max_render_chars` (4,000 by default).

The type's JSON Schema, from Pydantic, is given to the agent once, in the description of the `create_artifact` tool. Field descriptions (`Field(description=...)`) therefore reach the model.

## Summaries of changes

Every change carries a one-line summary that people and agents see in change notes, such as *"Alice changed plan_1 (plan, v7 → v8): completed Ship v1"*. The summary comes from the first of these that gives one:

1. The command's own `summary`, as in `plan.edit(fn, summary="moved the launch")` or the agent's `edit_text(..., summary=...)`.
2. The type's `describe_change(before)` hook, which sees the previous state.
3. A description generated from the patch, such as `add /tasks/task_3f9c...` or `edited text (1 replacement)`.

`describe_change` returns `None` when it has nothing specific to say, and the next source is used:

```python
from typing import Self


class Plan(Artifact):
    tasks: dict[str, Task] = {}

    def describe_change(self, before: Self) -> str | None:
        done = [
            task.title
            for task_id, task in self.tasks.items()
            if task.status == "done"
            and task_id in before.tasks
            and before.tasks[task_id].status != "done"
        ]
        return f"completed {', '.join(done)}" if done else None
```

Annotate `before` as `Self` in your override; it is always an instance of the same type.

## Markdown documents

`MarkdownArtifact` is a ready-made base for documents: one Markdown `text` field, rendered to the agent as-is. Subclass it, adding fields if you need them:

```python
class Brief(MarkdownArtifact):  # registered as "brief"
    title: str = ""
```

Documents are edited with **anchored text edits**: replace an exact passage that occurs exactly once. This is the edit language models perform most reliably, and it survives other people's edits elsewhere in the document. `Versioned.edit_text` builds one:

```python
brief = await ws.get(Brief, "brief")
await ws.commit(brief.edit_text("We ship on Friday.", "We ship on Monday."))
```

The edit is rejected with `PatchFailed` if the anchor does not occur (`the anchor '...' is not found`) or occurs more than once (`... is ambiguous: it occurs 3 times`). An empty anchor is allowed only to write into an empty field. Text edits work on any string field; pass `field=` to choose one other than `text`. The agent's generic `edit_text` tool uses the same edit, so any `MarkdownArtifact` is editable by the agent without application tools.

## How changes are expressed

The library defines two patch kinds, and artifact types cannot add their own:

- **JSON Patch** ([RFC 6902](https://www.rfc-editor.org/rfc/rfc6902)) over the artifact's JSON data, for any type. `Versioned.edit(fn)` is the usual way to make one: it deep-copies the data, lets `fn` change the copy in place, and diffs the result into a patch based on the version you read. `fn`'s return value is ignored.
- **Text edits** (`TextEdits`), anchored replacements in one text field, described above.

```python
plan = await ws.get(Plan, "plan_1")
await ws.commit(plan.edit(lambda p: p.add_task("Write the changelog")))
```

Agents do not write JSON Patch themselves. Give them domain tools (`add_task`, `set_status`) that make edits like the one above; see [The agent](agent.md#application-tools).

Clients that send commands over the wire write patches directly, as in `{"kind": "json_patch", "ops": [{"op": "replace", "path": "/goal", "value": "Ship v2"}]}`. The [thread protocol](../protocol.md#event-durable) describes both forms.

## Validation

Every change is validated: the patch is applied to the current data, and the result must validate against the type. A change that does not is rejected with `ValidationFailed`, whose `errors` are Pydantic's errors as JSON, so clients and the agent can see exactly what was wrong. Validators, constraints and coercion on your model all apply. If validation normalizes the data (coercing `"3"` to `3`, say), the revision records a patch that produces exactly what was stored.
