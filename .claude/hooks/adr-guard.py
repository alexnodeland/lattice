"""Before an edit to an accepted ADR, asks the user unless the edit only does what lattice allows.

An ADR once accepted keeps its body. What may change is its bold header lines (**Status:**,
**Amends:**, **Superseded by:** and the like), and what may be added is an amendment, or a note,
after the end of the body, as `## Amendment (YYYY-MM-DD)` sections are. Any other change asks the
user, who can still allow it, such as a link whose target moved; a new decision is a new ADR.
"""

import json
import re
import sys
from pathlib import Path

ADR = re.compile(r"(^|/)docs/(.+/)?adr/\d{4}-[^/]+\.md$")
HEADER = re.compile(r"^\*\*[^*]+:\*\*")
STATUS = re.compile(r"^\*\*Status:\*\*\s*(Accepted|Deprecated|Superseded)")


def _proposed(tool: str, tool_input: dict[str, object], text: str) -> str | None:
    if tool == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
    if not isinstance(edits, list):
        return None
    for edit in edits:
        if not isinstance(edit, dict):
            return None
        old, new = edit.get("old_string"), edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text


def _body(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if not HEADER.match(line)]


def main() -> None:
    """Read the hook's event from stdin, and print a decision to ask when the edit isn't allowed."""
    event = json.load(sys.stdin)
    tool_input = event.get("tool_input", {})
    path = Path(tool_input.get("file_path", ""))
    if not ADR.search(path.as_posix()) or not path.is_file():
        return
    text = path.read_text()
    if not any(STATUS.match(line) for line in text.splitlines()):
        return
    new = _proposed(event.get("tool_name", ""), tool_input, text)
    if new is not None:
        before, after = _body(text), _body(new)
        while before and not before[-1]:
            before.pop()
        if after[: len(before)] == before:
            return
    reason = (
        f"{path.name} is accepted: its body stays as it was. Change only its bold header lines "
        "(Status, Amends, Superseded by), append a dated `## Amendment (YYYY-MM-DD)` section, "
        "or write a new ADR that supersedes it (the new-adr skill)."
    )
    decision = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }
    sys.stdout.write(json.dumps({"hookSpecificOutput": decision}) + "\n")


if __name__ == "__main__":
    main()
