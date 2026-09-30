"""The artifact types, as plain Pydantic models."""

import pytest

from docplan.artifacts import Doc, Plan


def test_a_doc_shows_its_title_as_a_heading() -> None:
    assert Doc(title="Launch", text="We ship Friday.").render_for_agent() == (
        "# Launch\n\nWe ship Friday."
    )
    assert Doc(text="Untitled.").render_for_agent() == "Untitled."


def test_a_plan_tracks_tasks_and_statuses() -> None:
    plan = Plan(goal="Ship search", doc_id="art_doc")
    announce = plan.add_task("Write the announcement", owner="alice")
    index = plan.add_task("Build the index")
    plan.set_status(index, "doing")
    assert plan.render_for_agent().splitlines() == [
        "Goal: Ship search",
        "Implements: art_doc",
        f"- [ ] Write the announcement ({announce}, alice)",
        f"- [~] Build the index ({index})",
    ]
    with pytest.raises(KeyError):
        plan.set_status("task_nope", "done")
    assert Plan().render_for_agent() == "Goal: (none yet)"


def test_a_plan_describes_its_changes() -> None:
    before = Plan(goal="Ship search")
    task = before.add_task("Build the index")
    after = before.model_copy(deep=True)
    assert after.describe_change(before) is None
    after.goal = "Ship search in May"
    after.set_status(task, "done")
    after.add_task("Write the announcement")
    assert after.describe_change(before) == (
        "added 'Write the announcement'; 'Build the index' is done; goal: 'Ship search in May'"
    )
