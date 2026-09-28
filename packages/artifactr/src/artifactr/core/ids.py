"""Identifier types and factories.

Identifiers are plain strings; the aliases below document which kind of thing a string
identifies. Generated identifiers carry a short type prefix, such as ``thr_3f9c2a1b7d4e5f60``,
so they read well in logs and on the wire, but any string the host application chooses works.

Commands carry the identifiers of anything they create, which keeps the rules in
`artifactr.core` deterministic: the same command applied to the same state always produces the
same result.
"""

import secrets

type TenantId = str
"""Identifies a tenant: the top-level isolation boundary."""

type WorkspaceId = str
"""Identifies a workspace within a tenant."""

type ArtifactId = str
"""Identifies an artifact within a workspace."""

type ThreadId = str
"""Identifies a thread (a chat) within a workspace."""

type RunId = str
"""Identifies one agent run, which may span pauses."""

type ProposalId = str
"""Identifies a proposal."""

type MessageId = str
"""Identifies a message in a thread."""


def new_id(prefix: str) -> str:
    """Return a new random identifier with the given prefix.

    Args:
        prefix: A short type tag, such as ``"thr"``.

    Returns:
        An identifier such as ``thr_3f9c2a1b7d4e5f60``.
    """
    return f"{prefix}_{secrets.token_hex(8)}"


def new_artifact_id() -> ArtifactId:
    """Return a new artifact identifier."""
    return new_id("art")


def new_thread_id() -> ThreadId:
    """Return a new thread identifier."""
    return new_id("thr")


def new_run_id() -> RunId:
    """Return a new run identifier."""
    return new_id("run")


def new_proposal_id() -> ProposalId:
    """Return a new proposal identifier."""
    return new_id("prp")


def new_message_id() -> MessageId:
    """Return a new message identifier."""
    return new_id("msg")
