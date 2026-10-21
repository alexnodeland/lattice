"""grantr's real roles over artifactr's real catalog: who may run code in a connected app."""

from artifactr.workspace import ACTIONS
from grantr.core import Catalog

RUN_CODE = "artifactr:run_connected_code"


def test_admins_may_run_connected_code_and_no_editor_viewer_or_application_may() -> None:
    roles = Catalog.of(ACTIONS).built_in
    assert RUN_CODE in ACTIONS
    holding = {role for role, actions in roles.items() if RUN_CODE in actions}
    assert holding == {("tenant", "owner"), ("tenant", "admin"), ("workspace", "admin")}
