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
"""grantr's actions the deployment's operators hold, and no one else."""

RESTRICT: Final = "grantr:restrict"
"""Restricting a thread or artifact: whoever may, sees every restricted item where they may."""

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

MEMBERS_READS: Final = frozenset({"artifactr:read_workspaces"})
"""The tenant-wide reads every member of a tenant may ask: listings whose results the library
filters by what the caller may open."""

TENANT_ADMIN_READS: Final = frozenset({"portalr:read_telemetry", "portalr:read_spend"})
"""A tenant's telemetry and spend, in portalr's admin: its owners' and admins' to read."""

DEPLOYMENT_READS: Final = frozenset({"portalr:read_deployment"})
"""The whole deployment's telemetry, in portalr's admin: its operators' to read."""

ABOVE_WORKSPACES: Final = MEMBERS_READS | TENANT_ADMIN_READS | DEPLOYMENT_READS
"""The reads asked of a tenant or of the deployment, where no workspace role reaches: no
workspace role holds them, whatever their prefix. The application lists a tenant's workspaces,
but reads no portalr admin's telemetry or spend."""

CODE_RULE_WRITES: Final = frozenset(
    {
        "artifactr:propose_change",
        "artifactr:post_message",
        "artifactr:create_artifact",
        "artifactr:edit_artifact",
        "artifactr:create_thread",
    }
)
"""What the application's code rules write in artifactr, through relayr's outbound adapter:
proposals and notices, and the artifacts, keyed edits and threads their allowlists grant."""

RULE_INSTALLS: Final = frozenset(
    {"reflexr:install_rule", "reflexr:update_rule", "reflexr:archive_rule"}
)
"""What relayr's ``install-rule`` code rule does in reflexr: install, update and archive the
stored rules people accepted in chat, once relayr has checked that the person may."""

RUNTIME: Final = (
    BOOKKEEPING
    | CODE_RULE_WRITES
    | RULE_INSTALLS
    | {
        "artifactr:record",
        "reflexr:publish",
        "reflexr:checkpoint_run",
    }
)
"""The commands the application's ``application`` role holds, beside every ``open``, every read
and its evaluators' feedback: its bookkeeping, the runner's records, its code rules' runs, in
reflexr and, through relayr, in artifactr, and the stored rules relayr installs."""

RULE: Final = frozenset(
    {
        "reflexr:open",
        "reflexr:publish",
        "reflexr:checkpoint_run",
        "reflexr:read_events",
        "reflexr:read_runs",
    }
)
"""What a stored rule's ``rule`` role holds: opening its workspace, publishing events,
checkpointing its runs, and reading the log and its runs, as its actions do."""

type Level = Literal["deployment", "tenant", "workspace", "item"]
"""Where a role is granted: a thread, an artifact and a rule are each an item."""

BUILT_IN: Final = frozenset(
    {"operator", "application", "owner", "admin", "member", "editor", "viewer", "rule"}
)
"""The built-in roles' names, which no custom role may take."""

CUSTOM_LEVELS: Final[frozenset[Level]] = frozenset({"workspace", "item"})
"""Where a custom role may be granted: wherever a built-in workspace role can."""

MEMBER: Final = "member"
"""The role that makes a user or service principal a member of a tenant, and lets them list
what in it they may open."""

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
            ValueError: If an action isn't ``<library>:<name>``, or a library's catalog lacks
                a bookkeeping action, which would then not be kept out of people's roles.
        """
        actions = GRANTR_ACTIONS.union(*catalogs)
        if malformed := sorted(a for a in actions if not ACTION.fullmatch(a)):
            raise ValueError(f"actions are <library>:<name>, not {', '.join(malformed)}")
        present = {action.partition(":")[0] for action in actions}
        if missing := sorted(a for a in BOOKKEEPING - actions if a.partition(":")[0] in present):
            raise ValueError(f"the catalogs lack the bookkeeping {', '.join(missing)}")
        libraries = actions - GRANTR_ACTIONS
        reads = {
            action
            for action in libraries
            if action.partition(":")[2].startswith("read_") or action.endswith(":open")
        }
        viewer = (FEEDBACK & libraries | reads) - BOOKKEEPING - ABOVE_WORKSPACES
        editor = viewer | EDITOR_COMMANDS & libraries
        owner = actions - OPERATOR - BOOKKEEPING - DEPLOYMENT_READS
        return cls(
            actions=actions,
            built_in={
                ("deployment", "operator"): OPERATOR | DEPLOYMENT_READS & actions,
                ("deployment", APPLICATION): frozenset(
                    reads - TENANT_ADMIN_READS - DEPLOYMENT_READS | (RUNTIME | FEEDBACK) & libraries
                ),
                ("tenant", "owner"): owner,
                ("tenant", "admin"): owner - {"grantr:delete_tenant"},
                ("tenant", MEMBER): MEMBERS_READS & libraries,
                ("workspace", "admin"): libraries - BOOKKEEPING - ABOVE_WORKSPACES
                | WORKSPACE_GRANTS,
                ("workspace", "editor"): editor,
                ("workspace", "viewer"): viewer,
                ("workspace", "rule"): RULE & libraries,
                ("item", "editor"): editor,
                ("item", "viewer"): viewer,
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
