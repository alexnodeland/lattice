"""Roles: named sets of actions, built in or a tenant's own, resolved against the catalogs.

An action is a qualified string, ``<library>:<name>``. The application hands grantr each
library's catalog, the complete list of its actions, and grantr adds its own. A built-in role is
defined by action names and prefixes, so it holds what the catalogs it is handed contain: a
library's new read lands in ``viewer`` by its ``read_`` prefix, and a new command lands in no
built-in role until the role is changed here.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from grantr.core.errors import Invalid
from grantr.core.resources import ResourceKind

ACTION: Final = re.compile(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*")
"""An action's form: its library, a colon, and its name."""

GRANTR_ACTIONS: Final = frozenset(
    f"grantr:{name}"
    for name in (
        "create_tenant",
        "delete_tenant",
        "add_member",
        "remove_member",
        "manage_groups",
        "define_role",
        "grant",
        "revoke",
        "issue_key",
        "revoke_key",
        "restrict",
        "read_audit",
        "grant_operator",
    )
)
"""grantr's own catalog: the actions that change access, and read its audit log."""

OPERATOR: Final = frozenset({"grantr:create_tenant", "grantr:grant_operator"})
"""What the deployment's operators hold, and no one else."""

WORKSPACE_GRANTS: Final = frozenset({"grantr:grant", "grantr:revoke", "grantr:restrict"})
"""grantr's actions a workspace's admins hold within it."""

FEEDBACK: Final = frozenset({"artifactr:give_feedback", "reflexr:give_feedback"})
"""The commands a viewer may send: feedback on what they read."""

EDITOR_COMMANDS: Final = frozenset(
    {
        "artifactr:create_thread",
        "artifactr:post_message",
        "artifactr:answer_deferred",
        "artifactr:set_focus",
        "artifactr:set_thread_mode",
        "artifactr:create_artifact",
        "artifactr:edit_artifact",
        "artifactr:propose_change",
        "artifactr:archive_artifact",
        "artifactr:respond_to_proposal",
        "artifactr:stop_run",
        "artifactr:record",
        "reflexr:publish",
        "reflexr:retry_run",
        "reflexr:skip_run",
        "reflexr:cancel_run",
    }
)
"""The commands an editor may send beyond a viewer's: post, create, edit, propose, archive,
resolve proposals, and operate runs, and ``artifactr:record``, which a turn that an editor's
message starts asks as them. Rule management is the workspace admin's alone."""

BOOKKEEPING: Final = frozenset(
    {
        "artifactr:claim_thread",
        "artifactr:save_cursor",
        "artifactr:read_cursors",
        "reflexr:save_cursor",
        "reflexr:read_cursors",
    }
)
"""What the application's own machinery does, and no person's role holds: claiming threads, and
keeping the log's consumers' cursors."""

RUNTIME: Final = BOOKKEEPING | {
    "artifactr:record",
    "reflexr:publish",
    "reflexr:checkpoint_run",
}
"""The commands the application's ``application`` role holds, beside every ``open`` and read:
its bookkeeping, the runner's records, and its code rules' runs."""

RULE: Final = frozenset({"reflexr:open", "reflexr:publish", "reflexr:checkpoint_run"})
"""The commands a stored rule's ``rule`` role holds, beside reflexr's reads."""

type Level = Literal["deployment", "tenant", "workspace", "item"]
"""Where a role is granted: a thread, an artifact and a rule are each an item."""

BUILT_IN: Final = frozenset(
    {"operator", "application", "owner", "admin", "member", "editor", "viewer", "rule"}
)
"""The built-in roles' names, which no custom role may take."""

CUSTOM_LEVELS: Final[frozenset[Level]] = frozenset({"workspace", "item"})
"""Where a custom role may be granted: wherever a built-in workspace role can."""

MEMBER: Final = "member"
"""The role that makes a user or service principal a member of a tenant, and nothing more."""

APPLICATION: Final = "application"
"""The role of the application's own service principal: granted on the deployment, and the one
deployment role that holds in every tenant."""


LEVELS: Final[Mapping[ResourceKind, Level]] = {
    "deployment": "deployment",
    "tenant": "tenant",
    "workspace": "workspace",
    "thread": "item",
    "artifact": "item",
    "rule": "item",
}
"""The level a resource of each kind is at."""


class Role(BaseModel):
    """A tenant's own role: a named set of the actions a workspace's admin holds."""

    model_config = ConfigDict(frozen=True)

    name: str
    actions: frozenset[str]


@dataclass(frozen=True)
class Catalog:
    """Every action the application handed grantr, and the built-in roles over them."""

    actions: frozenset[str]
    built_in: Mapping[tuple[Level, str], frozenset[str]]
    """Each built-in role's actions, by the level it is granted at and its name."""

    @classmethod
    def of(cls, *catalogs: Iterable[str]) -> "Catalog":
        """The catalog of the libraries' catalogs and grantr's.

        Raises:
            ValueError: If an action isn't ``<library>:<name>``.
        """
        actions = GRANTR_ACTIONS.union(*catalogs)
        if malformed := sorted(a for a in actions if not ACTION.fullmatch(a)):
            raise ValueError(f"actions are <library>:<name>, not {', '.join(malformed)}")
        libraries = actions - GRANTR_ACTIONS
        reads = {
            action
            for action in libraries
            if action.partition(":")[2].startswith("read_") or action.endswith(":open")
        }
        viewer = (FEEDBACK & libraries | reads) - BOOKKEEPING
        editor = viewer | EDITOR_COMMANDS & libraries
        rule = {a for a in reads - BOOKKEEPING if a.startswith("reflexr:")} | RULE & libraries
        owner = actions - OPERATOR - BOOKKEEPING
        return cls(
            actions=actions,
            built_in={
                ("deployment", "operator"): OPERATOR,
                ("deployment", APPLICATION): frozenset(reads | RUNTIME & libraries),
                ("tenant", "owner"): owner,
                ("tenant", "admin"): owner - {"grantr:delete_tenant"},
                ("tenant", MEMBER): frozenset(),
                ("workspace", "admin"): libraries - BOOKKEEPING | WORKSPACE_GRANTS,
                ("workspace", "editor"): editor,
                ("workspace", "viewer"): viewer,
                ("workspace", "rule"): frozenset(rule),
                ("item", "editor"): editor,
                ("item", "viewer"): viewer,
                ("item", "rule"): frozenset(rule),
            },
        )

    def role(
        self, name: str, kind: ResourceKind, custom: Mapping[str, Role]
    ) -> frozenset[str] | None:
        """A role's actions, granted on a resource of this kind; None if it can't be there."""
        at = LEVELS[kind]
        if (at, name) in self.built_in:
            return self.built_in[at, name]
        if name in custom and at in CUSTOM_LEVELS:
            return custom[name].actions
        return None

    def check(self, role: Role) -> None:
        """Check a custom role against the catalogs.

        Raises:
            Invalid: If it takes a built-in role's name, holds no action, or holds one a
                workspace's admin doesn't: a custom role is granted in a workspace.
        """
        if role.name in BUILT_IN:
            raise Invalid(f"{role.name} is a built-in role")
        if not role.actions:
            raise Invalid(f"{role.name} holds no action")
        if unknown := sorted(role.actions - self.built_in["workspace", "admin"]):
            raise Invalid(f"{role.name} holds actions it can't: {', '.join(unknown)}")
