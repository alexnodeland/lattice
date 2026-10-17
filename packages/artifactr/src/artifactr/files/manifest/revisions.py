"""A revision of a native file: JSON Patch that tests the digest it was made from (ADR-0072).

A stale direct edit fails on its `base_version`, as `VersionConflict`. A proposal is re-applied
to the head when it is accepted, and acceptance checks no version, so the patch's first
operation tests the content's digest: accepting a stale proposal fails with `PatchFailed`
rather than replacing what came after.
"""

from typing import Final

from artifactr.core import ArtifactId, EditArtifact, JsonPatch, ThreadId
from artifactr_files.manifest.types import NativeFile

REVISED: Final = ("content", "provenance", "fingerprint", "text", "review", "outline", "pages")
"""What a revision replaces: everything in the manifest but the file's name."""


def revise(
    artifact_id: ArtifactId,
    after: NativeFile,
    *,
    base_version: int,
    tested: str,
    summary: str,
    thread_id: ThreadId | None = None,
) -> EditArtifact:
    """Build the edit that gives an artifact `after`'s content, if its content is `tested`.

    Args:
        artifact_id: The native file to revise.
        after: The manifest it is to have; its name is not changed.
        base_version: The version the edit is based on.
        tested: The content digest the edit was made from, which the patch tests first.
        summary: The change note, from the batch or the check-in.
        thread_id: The thread the edit is made in, if any.
    """
    data = after.to_json()
    return EditArtifact(
        artifact_id=artifact_id,
        base_version=base_version,
        patch=JsonPatch(
            ops=(
                {"op": "test", "path": "/content/sha256", "value": tested},
                *({"op": "replace", "path": f"/{name}", "value": data[name]} for name in REVISED),
            )
        ),
        summary=summary,
        thread_id=thread_id,
    )
