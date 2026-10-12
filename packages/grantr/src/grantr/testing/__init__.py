"""What every role holds, as a table an application commits.

An application prints :func:`matrix` over the catalogs it hands :class:`~grantr.grants.Grants`
and its custom roles, commits the table, and a test compares the two. A library's new action, or
a change to a role, then changes the table, and the change is reviewed with the code.
"""

from collections.abc import Iterable

from grantr.core import Catalog, Role


def matrix(catalogs: Iterable[Iterable[str]], roles: Iterable[Role] = ()) -> str:
    """Every role against every action in the catalogs, as a Markdown table.

    A column is a built-in role where it is granted, then each custom role. A built-in role
    granted on items holds there what it holds on their workspace, so it has one column.

    Raises:
        Invalid: If a custom role isn't valid against the catalogs.
    """
    catalog = Catalog.of(*catalogs)
    columns = [
        (f"{name} ({level})", actions)
        for (level, name), actions in catalog.built_in.items()
        if level != "item"
    ]
    for role in roles:
        catalog.check(role)
        columns.append((f"{role.name} (custom)", role.actions))
    lines = [
        "| Action | " + " | ".join(name for name, _ in columns) + " |",
        "|---|" + "---|" * len(columns),
        *(
            f"| `{action}` | "
            + " | ".join("✓" if action in actions else "" for _, actions in columns)
            + " |"
            for action in sorted(catalog.actions)
        ),
    ]
    return "\n".join(lines) + "\n"
