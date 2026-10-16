# ADR-0037: The state host's ClickHouse backups

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland

Carries [ADR-0027](0027-the-single-hosts-backups.md)'s ClickHouse backups and their restore drill over to the AWS recipe's state host ([#149](https://github.com/alexnodeland/lattice/issues/149)), with the alerts that watch them. It amends [ADR-0032](0032-the-edge-the-services-and-the-state-host.md), which left the state host with DLM's snapshots alone, and [ADR-0036](0036-tier-2-against-floci.md)'s account of what tier 2 runs.

## Context

The single host backs ClickHouse up with `BACKUP ... TO S3` through a `backups` named collection, as a `backup` user, nightly from a systemd timer, and proves the backup restores in a weekly drill. The state host keeps ClickHouse and Prometheus on one EBS volume, which DLM snapshots daily and keeps 14 of. Those snapshots are crash-consistent: ClickHouse recovers from one as from a power cut, which is not a restore that has been tried.

Four things weren't settled: how ClickHouse gets credentials for the bucket, what the instance's role may do there, how long the backups are kept, and where the alerts live. Floci can't run the EC2 state host, so what tier 2 can show is limited too.

## Decision

### Where it runs

- **On the state host,** from two systemd timers installed by its user data: `stackr-state-backup` nightly at 03:00 UTC, and `stackr-state-restore-drill` on Sundays at 05:00, after the backup. `deploy/aws/state-host/backup` and `restore-drill` are ADR-0027's scripts for ClickHouse alone: PostgreSQL is RDS's, and Prometheus stays on DLM's snapshots.
- **ClickHouse has the single host's `backup` user,** mounted from `deploy/host/clickhouse/backup-user.xml`, and a `backups` named collection (`deploy/aws/state-host/clickhouse/backups.xml`) that holds the bucket's URL and no key. Its password is a secret of its own, `clickhouse-backup-password`, read with the others each time the state host's unit starts.
- **Each backup is whole,** of Langfuse's database and the drill's, as `clickhouse/<UTC time>`. The drill's own backups go under `drill/<sentinel>`.
- **The bucket is `data`'s backups bucket,** private, encrypted with S3's own keys (SSE-S3), versioned, TLS-only. A customer-managed key and S3 Object Lock are left for later.

### Credentials: the host hands them over, per run

- **The scripts fetch the instance role's temporary credentials from IMDS on the host's own network, and pass them in each statement:** `S3(backups, 'clickhouse/<time>', access_key_id = …, secret_access_key = …, session_token = …)`. On ClickHouse 26.9.3, which the state host pins, the named collection accepts that override and sends the token as `x-amz-security-token`, checked against a server that records the requests.
- **IMDS's hop limit stays 1,** as [ADR-0032](0032-the-edge-the-services-and-the-state-host.md) has it: the containers on the host still can't reach the role. Raising it to 2, so that ClickHouse could use the role itself, would have let Prometheus and prom-label-proxy assume it as well.
- **The credentials are in no command line, file or environment.** A statement goes to `clickhouse-client` on standard input, and the scrub's `sed`, which lives as long as the statement, takes its script from a process substitution (`sed -f /dev/fd/N`), so no `ps` or `/proc/<pid>/cmdline` shows a credential: a test lists every process's arguments while a statement runs. The 60-second IMDS session token, which fetches the credentials, reaches `curl` the same way, as a header read from a descriptor. IMDS credentials that are already expired stop the run at once. The client quotes a failed statement in its error, so `scrub` takes the credentials out of its errors before they reach the journal; a test fails if it doesn't. The credentials are checked to be only what S3 gives out before they go into SQL.
- **They are fetched again before they run short.** The drill reaches the bucket four times over up to two hours, and the role's credentials last hours but not for ever. `imds-credentials` also prints when they expire, and before each statement the scripts fetch them again if less than 30 minutes remain (`STATE_MIN_CREDENTIAL_SECONDS`). IMDS rotates a role's credentials some time before they expire, so when it still hands out ones about to, the script waits for the rotation, and fails the run if the second fetch is as short. A fake IMDS tests each.
- **Where ClickHouse records a statement, it hides the secret and the session token, and not the access key id.** On 26.9.3, with a backup and a drill each held in flight by a slow S3 stand-in and then finished, `system.processes`, `system.backups.name`, `system.query_log`, `system.text_log`, the persisted server log files and the container's log showed `secret_access_key = '[HIDDEN]'` and `session_token = '[HIDDEN]'` for both forms, `BACKUP`/`RESTORE ... S3(backups, ...)` and `SELECT ... FROM s3(backups, ...)`, and neither value was found anywhere in them. The access key id is shown in the clear, as in the AWS console and CloudTrail: it identifies the credentials and isn't one. The check was a one-off on that version, not a test: an upgrade that changes the masking would not fail a build, so an upgrade of ClickHouse repeats it.

### What the role may do

- **It writes and reads `clickhouse/*` and `drill/*` of the backups bucket** (`s3:PutObject`, `s3:GetObject`, `s3:AbortMultipartUpload`).
- **It deletes nothing but ClickHouse's own lock files,** at the exact paths `clickhouse/<time>/.lock` and `drill/<sentinel>/.lock` (`?` stands for one character, so `*` can't cross a `/`), which ClickHouse writes and removes around each backup. It has no `s3:DeleteObjectVersion`.
- **It may list the bucket, with no prefix condition.** S3 answers a HEAD or GET of a missing key with 403 unless the caller may list, and ClickHouse checks for keys that don't exist (a backup's `.lock`, before it writes one). The host can therefore list the key names across the bucket, which are timestamps and drill names: it still cannot read another prefix's objects, since `GetObject` is limited to the two prefixes, and the bucket holds only these backups. That is accepted for a 404 that behaves.
- **What holds, exactly:** the host is delete-proof. It cannot delete a backup or a version of one. It can overwrite an object in its prefixes, and the overwritten version is recoverable for 7 days, until the lifecycle rule expires noncurrent versions. After 7 days a silent overwrite is permanent: S3 Object Lock is what would stop that, and is under Next.
- **A junk backup can be the "latest",** and that is the one thing the role does not stop. A compromised host can write `clickhouse/9999-12-31T23-59-59Z/.backup`, and the drill chooses the latest backup by name. The drill leaves out of its choice of the latest any name dated more than an hour ahead (compared as text, so a year beyond 2106 can't overflow), still drills the real latest, and then fails, saying so, so that the alert fires without a junk name hiding the real backup for as long as it is kept. A junk backup dated just before now and newer than the real one would pass freshness, and the drill would then fail to restore it, or fail to find rows in every table the live database has, so the alert fires. A copy of a real earlier backup under a new name would pass: the drill then proves that backup restores, and the real ones are still in the bucket, until they expire. What bounds this is the host's own compromise, which the role can't make worse than that, and the alert on a failed drill.
- **ClickHouse's `BACKUP` and `RESTORE` were run against MinIO enforcing exactly this policy,** by the real scripts. They succeeded (the backup, the drill's two restores, and the `.lock` deletes at the narrowed paths), and the same user was refused a delete of a backup's data file and a write outside the two prefixes, and a HEAD of a missing key answered "does not exist" and not "access denied". The tier-1 tests hold the policy's exact statements. MinIO is not IAM: the manual apply on AWS is the last check.

### Retention

- **`clickhouse_backup_retention_days`, 14 by default,** a variable of `stack` and `envs/prod`, 2 to 365 whole days. The backups are whole each night, so what they cost is the size of Langfuse's database times the days kept. The default matches DLM's 14 snapshots.
- **The drill's backups are kept 7 days.**
- **Noncurrent versions of `clickhouse/` and `drill/` expire after 7 days,** and so do the delete markers ClickHouse's lock files leave. This is the overwrite window above, and without it versioning would keep each expired backup 30 days longer, from the bucket's general rule.
- **The cost,** with 14 days kept and 7 for noncurrent versions: backups are written once, so an expired backup's data stays for 7 days beyond its 14, and a backup's lock file leaves a delete marker and a noncurrent version of a few bytes. At worst the bucket holds the size of Langfuse's database times 21 or 22 (the lifecycle rules run daily, at UTC midnight) plus the drill's few kilobytes. The minimum of 2 days is so that last night's backup can't expire before tonight's is written.

### The drill, and its alerts

- **The drill proves the latest backup restores,** as ADR-0027's step 4: it is under 36 hours old; a sentinel row is written and backed up; the latest backup is restored beside Langfuse's database with rows in every table the live one has; the sentinel's backup is restored with the sentinel in it. It checks there is room first, and drops what it restored.
- **Both scripts report `stackr.backup.success` and `stackr.restore_drill.success`, 1 or 0,** from an exit trap, to the state host's own Prometheus over OTLP, so a run that fails part way still says so.
- **Four alerts are Prometheus's own rules,** `deploy/aws/state-host/alerts.yml`, with the single host's four names and wording: no backup has succeeded in 36 hours; the latest backup failed; the restore drill hasn't passed in eight days; the latest drill failed.
  - A 0 fires, and so does a metric that is missing for its whole window, so a backup that never ran, or stopped, is a failed backup.
  - They exist only where a state host does. Grafana-managed rules would have lived in the thin image every deployment runs, and fired "no data" for ever on Floci, which has none.
  - Grafana lists them under Alerting, as the Prometheus data source's rules, with their state: checked against the pinned Grafana and Prometheus, where a failed backup's rule fired.
  - No notification is sent, as on the single host: an operator adds an Alertmanager, or watches the list. Like the single host's, they carry no severity.
  - A new state host fires the first and third until its first backup and its first drill, as the single host's do. Run `sudo systemctl start stackr-state-backup` and `stackr-state-restore-drill` after the first apply: `Persistent=true` catches up a missed run only when the timer has run before, and a new host has no stamp, so its first backup would otherwise be at the next 03:00 UTC.
- **promtool tests the rules** (`alerts.test.yml`, run by `deploy/aws/check`): healthy, a failed latest run, nothing succeeded in the window, a metric that stopped arriving, a weekly drill not yet due and then overdue, and a host that has reported nothing. Each rule was changed in turn, to check the tests notice.

### Running them

- **A backup and a drill never overlap.** Both take one `flock` lock (`/run/lock/stackr-state-backups.lock`) and wait up to an hour for it, so a manual run can't collide with the timer, and the Sunday drill waits for the backup. A run that gives up waiting reports a failure and leaves the other run's restore databases alone. Both are run with `systemctl start`; running the files directly adds nothing.
- **The drill's `TimeoutStartSec` is 2 hours,** which includes the up to an hour it may wait for the lock, so it has less than the backup's 3 hours if both overrun.
- **The units `Want` `stackr-state.service`, and don't `Require` it,** so `systemctl restart stackr-state`, the documented secret-rotation action, doesn't stop a backup that is running.
- **They read a file of their own, `/run/stackr/backup.env`,** which holds the Prometheus address and none of ClickHouse's passwords, and run with `NoNewPrivileges`, `PrivateTmp` and `ProtectHome`. More (`ProtectSystem`, a private network) would stop `docker` or IMDS working.

### Tier 2

Floci can't run the EC2 state host ([ADR-0025](0025-what-the-floci-spike-found.md)), so on Floci ClickHouse is a Fargate task without the state host's config files. Tier 2 starts the state host's own ClickHouse image, labelled as the run's, with the state host's own `users.xml`, `backup-user.xml` and `backups.xml`, on the run's network. It points the collection at the backups bucket the apply made, in Floci's S3, runs `backup` and `restore-drill` as they are, and finds both metrics in the Prometheus Floci runs.

- **Tier 2 does not run:** IMDS and the credentials from it (Floci's static keys stand in); IAM's enforcement (Floci stores policies); the systemd units and the user data; and the alert rules, since the Prometheus on Floci has none.
- **Other tests do.** A fake IMDS tests the credentials; a table-driven fake of `docker` plays ClickHouse for the drill's failure paths (a stale or future-dated or missing backup, no room, a restored table without rows, a missing sentinel, the trap dropping the restore databases, a rerun after a killed run); the same tests test what the scripts send, the scrubbing, the lock and the metrics; tier 1 tests the policy, the lifecycle rules, the secret and the units; and promtool tests the rules.
- **The manual apply on real AWS** checks the rest. On a state host, check:
  - `systemctl start stackr-state-backup` succeeds, and so does a `RESTORE` from it: BACKUP and RESTORE against the real bucket under the real role, including ClickHouse's probes of keys that don't exist, which must come back 404 and not 403.
  - The exact `?` lock patterns match what ClickHouse really writes. ClickHouse may tolerate a failed delete of its lock file, so a backup that succeeded doesn't prove them: after the first backup, `aws s3api list-object-versions --prefix clickhouse/` shows no stray `.lock`, and CloudTrail no `AccessDenied` on `DeleteObject`.
  - `docker exec` works under `ProtectHome=true` and `NoNewPrivileges=true` on real systemd (root's `/root/.docker` becomes inaccessible).
  - `tofu apply` accepts the backups bucket's lifecycle rules, one pair per prefix beside the bucket's general rule.
  - `systemctl restart stackr-state` during a run does not stop the backup, which is the point of `Wants=`.
  - The drill passes, both metrics reach Prometheus, and the four rules are listed.
  - Grafana lists the rules through prom-label-proxy. Grafana's Prometheus data source is direct at `:9090`, so they should show; if the proxy is ever put in front, it may filter `/api/v1/rules`, which carries no tenant label.
  - The role cannot delete a backup: `aws s3 rm` of a backup's object, from the host, is refused.

### Deploying it

- **The state host is replaced once, by the next apply.** Its user data gains the timers, the `backup` password and the bucket's URL, and `user_data_replace_on_change` replaces the instance, as any `lattice_commit` bump does: minutes without traces in Langfuse and without metrics, the data volume attached again. It ships with the next scheduled `lattice_commit` bump, not on its own.
- **A new secret is made,** `clickhouse-backup-password`. Like ClickHouse's other passwords it reaches the state host only when its unit starts, so it isn't rotatable here.

### Restoring onto a new host

An operator's task, as in ADR-0027: on the state host, over a session, as ClickHouse's `admin`, `RESTORE DATABASE default FROM S3(backups, 'clickhouse/<time>', access_key_id = …, secret_access_key = …, session_token = …)`, with the credentials from `deploy/aws/state-host/imds-credentials`. Restoring a volume from DLM's snapshot remains the faster way back when the host is lost with its volume.

### Where this departs from ADR-0027

- **The credentials are the role's, handed over per run,** not keys in the collection from the environment.
- **The alerts are Prometheus's rules on the state host,** not Grafana-managed rules in the host overlay.
- **Only ClickHouse's half of the drill,** since PostgreSQL is RDS's, with its own automated backups.

## Options considered

| Option | For | Against |
|---|---|---|
| **The host hands ClickHouse the role's credentials per run (chosen)** | The hop limit stays 1; no long-lived secret | A little scripting; the credentials pass through a statement |
| IMDS's hop limit 2, ClickHouse uses the role | Simplest; ClickHouse refreshes the credentials | Every container on the host can assume the role: Prometheus, prom-label-proxy |
| An IAM user's keys in Secrets Manager | As the single host's keys are | A long-lived secret to rotate, against the issue's "instance role in place of keys" |
| **Prometheus's rules on the state host (chosen)** | Exist only where the metrics do; Grafana lists them | No notification without an Alertmanager |
| Grafana-managed rules in the thin image | A contact point could be set up in Grafana | Fire "no data" for ever where there is no state host, or hide a missing backup |
| **A role that deletes only lock files (chosen)** | A compromised host can't delete a backup or a version of one | The policy must name ClickHouse's lock files |
| A role that may delete in its prefixes | Simpler | A compromised host could delete the backups |
| **Noncurrent versions kept 7 days (chosen)** | An overwrite is recoverable for a week | Storage for a week more than the retention |
| Noncurrent versions gone after a day | Cheaper | An overwrite is recoverable for a day, hardly a weekend |

## Consequences

- Easier: the state host's ClickHouse has backups that are tried every week, and Grafana says when they stop passing.
- Harder: the state host is replaced once on deploy; whole nightly backups cost their size times the retention.
- Harder: the instance role is a thing to keep in step with what ClickHouse needs of S3: an upgrade that uses another call is found by the manual apply, or by the first nightly backup.
- Next: an Alertmanager or another way to be told; S3 Object Lock, which would make an overwrite unrecoverable by the host for good and close the 7-day window, and a customer-managed key, if the backups should resist more.
