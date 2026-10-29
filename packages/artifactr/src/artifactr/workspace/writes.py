"""Which kinds an agent's writes apply to directly in Auto: a setting (ADR-0009, ADR-0030).

An agent's create, edit or archive is a proposal in a thread in Ask. In Auto it applies directly
when its kind is in the application's ``agent-writes:direct`` setting, and is a proposal
otherwise. :func:`direct_writes` declares that setting over the application's types: by default
it holds the kinds whose ``write_policy`` is ``"direct"``, so nothing changes until someone sets
it. The operator's value, in the deployment's configuration, may add kinds; a tenant's and a
workspace's admins may only take kinds out, so a workspace never applies directly what its tenant
sends for review. Give :func:`direct_writes_from` to ``Workspaces(direct_writes=...)``.
"""

from collections.abc import Iterable
from typing import Final

from artifactr.core import Artifact, TenantId, WorkspaceId
from artifactr.workspace.workspace import DirectWrites
from lattice_core.settings import Setting, Settings, Subset

DIRECT_WRITES: Final = "agent-writes:direct"
"""The setting that names the kinds whose agents' writes apply directly in Auto."""


def direct_writes(types: Iterable[type[Artifact]]) -> Setting:
    """``agent-writes:direct``, for the settings registry, over the application's types.

    Its default is the kinds whose ``write_policy`` is ``"direct"``; each kind is labelled with
    what its type does by default.
    """
    kinds = {t.kind: t.write_policy for t in types}
    return Setting(
        DIRECT_WRITES,
        Subset(frozenset(kinds)),
        default=tuple(sorted(kind for kind, policy in kinds.items() if policy == "direct")),
        lowest="workspace",
        description=(
            "Which kinds of artifact an agent's edits apply to directly in Auto; the others wait"
            " for review, as every kind's do in Ask."
        ),
        labels={
            kind: "applies by default" if policy == "direct" else "reviewed by default"
            for kind, policy in kinds.items()
        },
    )


def direct_writes_from(settings: Settings) -> DirectWrites:
    """The kinds a settings store holds in ``agent-writes:direct``, read on each agent's write.

    A store that can't be read answers no kinds, so every agent's write is a proposal; a value
    that isn't names raises, and the write with it.
    """

    async def read(tenant_id: TenantId, workspace_id: WorkspaceId) -> frozenset[str]:
        value = await settings.value(tenant_id, workspace_id, DIRECT_WRITES)
        if not isinstance(value, tuple):
            raise TypeError(f"{DIRECT_WRITES} holds names")
        return frozenset(value)

    return read
