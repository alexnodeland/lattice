import pytest

from grantr.core import Invalid, Role
from grantr.testing import matrix


def test_the_matrix_lists_every_action_against_every_role() -> None:
    table = matrix([{"lib:open", "lib:read_things", "lib:edit"}])
    header, rule, *rows = table.splitlines()
    assert header == (
        "| Action | operator (deployment) | application (deployment) | owner (tenant)"
        " | admin (tenant) | member (tenant) | admin (workspace) | editor (workspace)"
        " | viewer (workspace) | rule (workspace) |"
    )
    assert rule == "|---|" + "---|" * 9
    assert "| `lib:edit` |  |  | ✓ | ✓ |  | ✓ |  |  |  |" in rows
    assert "| `lib:open` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |" in rows
    assert len(rows) == 3 + 14, "every action, grantr's own included"


def test_the_matrix_has_a_column_per_custom_role() -> None:
    table = matrix([{"lib:open"}], [Role(name="opener", actions=frozenset({"lib:open"}))])
    assert table.splitlines()[0].endswith(" | opener (custom) |")
    assert "| `lib:open` |" in table
    with pytest.raises(Invalid, match="built-in"):
        matrix([{"lib:open"}], [Role(name="viewer", actions=frozenset({"lib:open"}))])
