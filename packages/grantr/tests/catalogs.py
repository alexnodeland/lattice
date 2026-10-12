"""Catalogs shaped like the libraries' ``ACTIONS``, for the tests."""

ARTIFACTR = frozenset(
    {
        "artifactr:open",
        "artifactr:read_artifacts",
        "artifactr:read_threads",
        "artifactr:give_feedback",
        "artifactr:post_message",
        "artifactr:edit_artifact",
        "artifactr:propose_change",
    }
)

REFLEXR = frozenset(
    {
        "reflexr:open",
        "reflexr:read_rules",
        "reflexr:read_runs",
        "reflexr:give_feedback",
        "reflexr:cancel_run",
        "reflexr:install_rule",
    }
)

PORTALR = frozenset({"portalr:read_telemetry"})
