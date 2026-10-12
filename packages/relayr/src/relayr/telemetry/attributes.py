"""The attributes relayr's spans and metrics carry, named as the libraries name theirs."""

from typing import Final

TENANT_ID: Final = "relayr.tenant.id"
WORKSPACE_ID: Final = "relayr.workspace.id"
EVENT_TYPE: Final = "relayr.event.type"
"""The artifactr event's type, such as `message_posted`."""

ENVELOPE_SEQ: Final = "relayr.envelope.seq"
"""The envelope's position in the artifactr workspace's log."""

ERROR_TYPE: Final = "error.type"
"""What stopped a follower: the type of its exception, in the semantic conventions' name."""
