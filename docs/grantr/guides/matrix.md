# The permission matrix

Every built-in role against every action of artifactr's, reflexr's and grantr's catalogs, where it is granted: what `grantr.testing.matrix` prints for the two libraries ([ADR-0011](../adr/0011-built-in-roles-over-the-catalogs.md)). A role granted on a thread, artifact or rule holds there what it holds on their workspace. A test checks this page against the catalogs, and fails when it is out of date. To regenerate it, replace the table with what this prints:

```bash
uv run python -c "from artifactr.workspace import ACTIONS as A; from reflexr.workspace import ACTIONS as R; from grantr.testing import matrix; print(matrix([A, R]), end='')"
```

An application's own, with its custom roles, is in its `access.md` ([Roles and grants](roles-and-grants.md#reviewing-who-may-do-what)).

| Action | operator (deployment) | application (deployment) | owner (tenant) | admin (tenant) | member (tenant) | admin (workspace) | editor (workspace) | viewer (workspace) | rule (workspace) |
|---|---|---|---|---|---|---|---|---|---|
| `artifactr:answer_deferred` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:archive_artifact` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:claim_thread` |  | ✓ |  |  |  |  |  |  |  |
| `artifactr:create_artifact` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:create_native_file` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:create_thread` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:edit_artifact` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:give_feedback` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `artifactr:open` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ |
| `artifactr:post_message` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ |
| `artifactr:propose_change` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:read_artifacts` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `artifactr:read_cursors` |  | ✓ |  |  |  |  |  |  |  |
| `artifactr:read_events` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `artifactr:read_history` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `artifactr:read_proposals` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `artifactr:read_runs` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `artifactr:read_threads` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `artifactr:read_workspaces` |  | ✓ | ✓ | ✓ | ✓ |  |  |  |  |
| `artifactr:record` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:respond_to_proposal` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:run_connected_code` |  |  | ✓ | ✓ |  | ✓ |  |  |  |
| `artifactr:save_cursor` |  | ✓ |  |  |  |  |  |  |  |
| `artifactr:set_focus` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:set_thread_mode` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `artifactr:stop_run` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `grantr:add_member` |  |  | ✓ | ✓ |  |  |  |  |  |
| `grantr:create_tenant` | ✓ |  |  |  |  |  |  |  |  |
| `grantr:define_role` |  |  | ✓ | ✓ |  |  |  |  |  |
| `grantr:delete_tenant` |  |  | ✓ |  |  |  |  |  |  |
| `grantr:grant` |  |  | ✓ | ✓ |  | ✓ |  |  |  |
| `grantr:grant_operator` | ✓ |  |  |  |  |  |  |  |  |
| `grantr:issue_key` |  |  | ✓ | ✓ |  |  |  |  |  |
| `grantr:manage_groups` |  |  | ✓ | ✓ |  |  |  |  |  |
| `grantr:manage_integrations` |  |  | ✓ | ✓ |  | ✓ |  |  |  |
| `grantr:read_audit` |  |  | ✓ | ✓ |  |  |  |  |  |
| `grantr:remove_member` |  |  | ✓ | ✓ |  |  |  |  |  |
| `grantr:restrict` |  |  | ✓ | ✓ |  | ✓ |  |  |  |
| `grantr:revoke` |  |  | ✓ | ✓ |  | ✓ |  |  |  |
| `grantr:revoke_key` |  |  | ✓ | ✓ |  |  |  |  |  |
| `reflexr:archive_rule` |  | ✓ | ✓ | ✓ |  | ✓ |  |  |  |
| `reflexr:cancel_run` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `reflexr:checkpoint_run` |  | ✓ | ✓ | ✓ |  | ✓ |  |  | ✓ |
| `reflexr:give_feedback` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `reflexr:install_rule` |  | ✓ | ✓ | ✓ |  | ✓ |  |  |  |
| `reflexr:open` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ |
| `reflexr:publish` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ |
| `reflexr:read_cursors` |  | ✓ |  |  |  |  |  |  |  |
| `reflexr:read_dead_letters` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `reflexr:read_events` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ |
| `reflexr:read_rules` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `reflexr:read_runs` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ |
| `reflexr:read_schedules` |  | ✓ | ✓ | ✓ |  | ✓ | ✓ | ✓ |  |
| `reflexr:replay_rule` |  |  | ✓ | ✓ |  | ✓ |  |  |  |
| `reflexr:retry_run` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `reflexr:save_cursor` |  | ✓ |  |  |  |  |  |  |  |
| `reflexr:skip_run` |  |  | ✓ | ✓ |  | ✓ | ✓ |  |  |
| `reflexr:update_rule` |  | ✓ | ✓ | ✓ |  | ✓ |  |  |  |
