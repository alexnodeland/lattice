"""The two artifact types: a Markdown document, and a plan of tasks."""

from typing import ClassVar, Literal, Self

from pydantic import BaseModel, Field

from artifactr import Artifact, MarkdownArtifact, WritePolicy, new_id

Status = Literal["todo", "doing", "done"]


class Doc(MarkdownArtifact):
    """A Markdown document. The agent edits it directly."""

    title: str = ""

    def render_for_agent(self) -> str:
        """Show the title as a heading above the text."""
        return f"# {self.title}\n\n{self.text}" if self.title else self.text


class Task(BaseModel):
    """One piece of work in a plan."""

    title: str
    status: Status = "todo"
    owner: str | None = None


class Plan(Artifact):
    """A plan of tasks. The agent proposes changes; a person accepts them."""

    write_policy: ClassVar[WritePolicy] = "propose"

    goal: str = ""
    doc_id: str | None = None
    """The document this plan implements."""

    tasks: dict[str, Task] = Field(default_factory=dict)

    def add_task(self, title: str, owner: str | None = None) -> str:
        """Add a task and return its id."""
        task_id = new_id("task")
        self.tasks[task_id] = Task(title=title, owner=owner)
        return task_id

    def set_status(self, task_id: str, status: Status) -> None:
        """Move a task to a status."""
        if task_id not in self.tasks:
            raise KeyError(f"the plan has no task {task_id}")
        self.tasks[task_id].status = status

    def render_for_agent(self) -> str:
        """Show the plan as a checklist, with task ids for the tools."""
        marks = {"todo": " ", "doing": "~", "done": "x"}
        lines = [f"Goal: {self.goal or '(none yet)'}"]
        if self.doc_id:
            lines.append(f"Implements: {self.doc_id}")
        lines += [
            f"- [{marks[t.status]}] {t.title} ({task_id}"
            + (f", {t.owner}" if t.owner else "")
            + ")"
            for task_id, t in self.tasks.items()
        ]
        return "\n".join(lines)

    def describe_change(self, before: Self) -> str | None:
        """Summarize added tasks and status changes."""
        changes = [f"added {t.title!r}" for i, t in self.tasks.items() if i not in before.tasks]
        changes += [
            f"{t.title!r} is {t.status}"
            for i, t in self.tasks.items()
            if i in before.tasks and before.tasks[i].status != t.status
        ]
        if self.goal != before.goal:
            changes.append(f"goal: {self.goal!r}")
        return "; ".join(changes) or None
