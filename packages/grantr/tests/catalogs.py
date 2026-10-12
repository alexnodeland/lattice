"""Catalogs shaped like the libraries' ``ACTIONS``, for the tests."""

ARTIFACTR = frozenset(
    {
        "artifactr:open",
        "artifactr:read_workspaces",
        "artifactr:read_artifacts",
        "artifactr:read_threads",
        "artifactr:read_events",
        "artifactr:give_feedback",
        "artifactr:post_message",
        "artifactr:edit_artifact",
        "artifactr:propose_change",
        "artifactr:stop_run",
        "artifactr:record",
        "artifactr:claim_thread",
        "artifactr:save_cursor",
        "artifactr:read_cursors",
    }
)

REFLEXR = frozenset(
    {
        "reflexr:open",
        "reflexr:read_rules",
        "reflexr:read_runs",
        "reflexr:read_events",
        "reflexr:give_feedback",
        "reflexr:cancel_run",
        "reflexr:install_rule",
        "reflexr:update_rule",
        "reflexr:archive_rule",
        "reflexr:publish",
        "reflexr:checkpoint_run",
        "reflexr:save_cursor",
        "reflexr:read_cursors",
    }
)

PORTALR = frozenset({"portalr:read_telemetry", "portalr:read_spend", "portalr:read_deployment"})
