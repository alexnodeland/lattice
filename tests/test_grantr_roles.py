"""grantr's roles name the libraries' actions as the libraries name them.

grantr imports neither library, so its role definitions name artifactr's and reflexr's actions as
strings. A library that renames an action would leave a role naming nothing; this test, which sees
every package, holds the names to the libraries' catalogs. portalr's actions are named as grantr
expects them until portalr's catalog exists (lattice RFC-0002's phase 4).
"""

from artifactr.workspace import ACTIONS as ARTIFACTR
from grantr.core import Catalog
from grantr.core.roles import (
    BOOKKEEPING,
    DEPLOYMENT_READS,
    EDITOR_COMMANDS,
    FEEDBACK,
    MEMBERS_READS,
    RULE,
    RUNTIME,
    TENANT_ADMIN_READS,
)
from reflexr.workspace import ACTIONS as REFLEXR


def test_every_action_a_role_names_is_in_a_librarys_catalog() -> None:
    named = BOOKKEEPING | EDITOR_COMMANDS | FEEDBACK | MEMBERS_READS | RULE | RUNTIME
    assert named - (ARTIFACTR | REFLEXR) == set()


def test_portalrs_admin_reads_are_named_as_portalr_will_name_them() -> None:
    assert {
        "portalr:read_telemetry",
        "portalr:read_spend",
        "portalr:read_deployment",
    } == TENANT_ADMIN_READS | DEPLOYMENT_READS


def test_relayrs_bridge_holds_what_it_does_as_the_application() -> None:
    application = Catalog.of(ARTIFACTR, REFLEXR).role("application", "deployment", {})
    assert application is not None
    assert {"artifactr:open", "artifactr:read_events", "reflexr:open", "reflexr:publish"} <= (
        application
    )
