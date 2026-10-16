"""The state host's ClickHouse backups (stackr ADR-0037), run offline.

The scripts run on the EC2 state host, which Floci can't stand in for, so these run them here
against stand-ins: a fake IMDS for the instance role's credentials, and a fake `docker` that plays
ClickHouse, recording what the scripts send and answering as a test scripts it. Tier 2 runs the
same scripts against a real ClickHouse and Floci's S3, and the manual apply on AWS runs them with
the real role.
"""

import configparser
import http.server
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pytest

STATE_HOST = Path(__file__).parent.parent / "packages" / "stackr" / "deploy" / "aws" / "state-host"
# These have the shape the scripts accept from S3, and none of any provider's key, so no secret
# scanner mistakes them for one. A suffix new to each run keeps another run's processes, on a
# machine that has several going, out of the test that searches `ps` for them.
_RUN = secrets.token_hex(6)
ACCESS = f"fixture-access-key-id-{_RUN}"
SECRET = f"fixture/secret+access-key={_RUN}"
TOKEN = f"fixture-session-token-{_RUN}/+=="
STAMP = "2026-10-15T03-00-00Z"
METRICS = {"backup": "stackr.backup.success", "restore-drill": "stackr.restore_drill.success"}


class FakeIMDS(http.server.BaseHTTPRequestHandler):
    """IMDSv2: a token by PUT, and everything else only with that token.

    `lives` is how many seconds each successive fetch of the credentials has left, the last one
    repeating; the access key id gets the fetch's number after the first, so a refetch shows.
    """

    role = "stackr-state-host"
    code = "Success"
    log: ClassVar[list[str]] = []
    lives: ClassVar[list[int]] = [21600]
    fetches = 0

    def _send(self, status: int, body: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())

    def do_PUT(self) -> None:
        self.log.append(
            f"PUT {self.path} ttl={self.headers.get('X-aws-ec2-metadata-token-ttl-seconds')}"
        )
        self._send(200, "a-session-token") if self.path == "/latest/api/token" else self._send(404)

    def do_GET(self) -> None:
        self.log.append(f"GET {self.path}")
        if self.headers.get("X-aws-ec2-metadata-token") != "a-session-token":
            return self._send(401)
        base = "/latest/meta-data/iam/security-credentials/"
        if self.path == base:
            return self._send(200, self.role)
        if self.path == base + self.role:
            fetch = type(self).fetches
            life = self.lives[min(fetch, len(self.lives) - 1)]
            expires = datetime.now(UTC) + timedelta(seconds=life)
            type(self).fetches += 1
            return self._send(
                200,
                json.dumps(
                    {
                        "Code": self.code,
                        "AccessKeyId": ACCESS if fetch == 0 else f"{ACCESS}{fetch}",
                        "SecretAccessKey": SECRET,
                        "Token": TOKEN,
                        "Expiration": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                ),
            )
        return self._send(404)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def imds() -> Iterator[str]:
    FakeIMDS.role, FakeIMDS.code, FakeIMDS.log = "stackr-state-host", "Success", []
    FakeIMDS.lives, FakeIMDS.fetches = [21600], 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeIMDS)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def run(script: str, environment: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(STATE_HOST / script)],
        env={"PATH": os.environ["PATH"], **environment},
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_roles_credentials_come_from_imdsv2_with_its_token_and_say_when_they_expire(
    imds: str, tmp_path: Path
) -> None:
    done = run("imds-credentials", {"IMDS_ENDPOINT": imds}, tmp_path)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[:3] == [ACCESS, SECRET, TOKEN]
    assert abs(int(lines[3]) - (time.time() + 21600)) < 5, (
        "the fourth line is when, in epoch seconds"
    )
    assert FakeIMDS.log[0] == "PUT /latest/api/token ttl=60"
    assert all(
        line.startswith("GET /latest/meta-data/iam/security-credentials/")
        for line in FakeIMDS.log[1:]
    )


def test_an_instance_without_a_role_or_with_a_refusal_gets_no_credentials(
    imds: str, tmp_path: Path
) -> None:
    FakeIMDS.role = ""
    done = run("imds-credentials", {"IMDS_ENDPOINT": imds}, tmp_path)
    assert done.returncode != 0
    assert "no role" in done.stderr
    FakeIMDS.role, FakeIMDS.code = "stackr-state-host", "AssumeRoleUnauthorizedAccess"
    done = run("imds-credentials", {"IMDS_ENDPOINT": imds}, tmp_path)
    assert done.returncode != 0
    assert SECRET not in done.stdout + done.stderr


def test_no_imds_is_a_failure_not_empty_credentials(tmp_path: Path) -> None:
    done = run("imds-credentials", {"IMDS_ENDPOINT": "http://127.0.0.1:9"}, tmp_path)
    assert done.returncode != 0
    assert done.stdout == ""


FAKE_DOCKER = r"""#!__PYTHON__
# A fake `docker exec -i <clickhouse> sh -c ...`: it records what it is given, and plays
# ClickHouse as the test's config.json scripts it. Ages are seconds before now.
import json, os, re, sys, time
fake = os.environ["FAKE"]
query = sys.stdin.read().strip()
with open(f"{fake}/docker.argv", "a") as argv:
    argv.write(" ".join(sys.argv[1:]) + "\n")
with open(f"{fake}/docker.stdin", "a") as stdin:
    stdin.write(json.dumps(query) + "\n")
config_path = f"{fake}/config.json"
config = json.load(open(config_path)) if os.path.exists(config_path) else {}
state_path = f"{fake}/state.json"
state = {"databases": config.get("existing", [])}
if os.path.exists(state_path):
    state = json.load(open(state_path))


def done(output="", code=0, error=None):
    json.dump(state, open(state_path, "w"))
    if error:
        sys.stderr.write(f"Code: 499. DB::Exception: {error} (query: {query})\n")
    sys.stdout.write(output + ("\n" if output else ""))
    sys.exit(code)


for needle in config.get("fail_matching", []):
    if needle in query:
        done(code=243, error="failed")
if config.get("delay_backup") and query.startswith("BACKUP DATABASE"):
    time.sleep(config["delay_backup"])
drop = re.match(r"DROP DATABASE IF EXISTS (\w+) SYNC", query)
if drop:
    state["databases"] = [name for name in state["databases"] if name != drop[1]]
    done()
restore = re.match(r"RESTORE DATABASE \S+ AS (\w+) FROM", query)
if restore:
    if restore[1] in state["databases"]:
        done(code=243, error=f"Database {restore[1]} already exists")
    if config.get("restore_fails"):
        done(code=243, error="Cannot restore")
    state["databases"].append(restore[1])
    done()
if query.startswith("SELECT countIf(name >"):
    done(f"{config.get('future', 0)}\t{config.get('latest', '')}")
if query.startswith("SELECT toUnixTimestamp(parseDateTimeBestEffort"):
    done(str(int(time.time()) - config.get("taken_age", 3600)))
if query.startswith("SELECT sum(bytes_on_disk)"):
    done(str(config.get("used", 1000)))
if query.startswith("SELECT free_space"):
    done(str(config.get("free", 10**9)))
tables = re.match(r"SELECT name FROM system.tables WHERE database = '(\w+)'", query)
if tables:
    done("\n".join(config.get("live_tables" if tables[1] == "default" else "restored_tables", [])))
if query.startswith("SELECT count() FROM restore_sentinel.sentinel"):
    done(str(config.get("sentinel_rows", 1)))
done()
"""


@pytest.fixture
def fakes(tmp_path: Path) -> Path:
    """A directory with a `docker` that plays ClickHouse, and a `curl` that records reports."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER.replace("__PYTHON__", sys.executable))
    # Not named curl: imds-credentials needs the real one, and STATE_CURL points the reports here.
    (bin_dir / "fake-curl").write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >>"$FAKE/curl.argv"\ncat >>"$FAKE/curl.stdin"\n'
    )
    for tool in bin_dir.iterdir():
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return tmp_path


def configure(fakes: Path, **config: Any) -> None:
    (fakes / "config.json").write_text(json.dumps(config))


def environment(fakes: Path, **more: str) -> dict[str, str]:
    return {
        "PATH": f"{fakes / 'bin'}:{os.environ['PATH']}",
        "FAKE": str(fakes),
        "STATE_BACKUP_CREDENTIALS": "env",
        "AWS_ACCESS_KEY_ID": ACCESS,
        "AWS_SECRET_ACCESS_KEY": SECRET,
        "AWS_SESSION_TOKEN": TOKEN,
        "STATE_PROMETHEUS_URL": "http://10.40.128.10:9090",
        "STATE_CURL": str(fakes / "bin" / "fake-curl"),
        "STATE_LOCK_FILE": str(fakes / "lock"),
        **more,
    }


def reported(fakes: Path) -> list[dict[str, Any]]:
    """The gauges the script sent: its OTLP bodies, one per call."""
    text = (fakes / "curl.stdin").read_text()
    decoder, bodies, start = json.JSONDecoder(), [], text.find('{"resourceMetrics"')
    while start != -1:
        body, end = decoder.raw_decode(text, start)
        bodies.append(body)
        start = text.find('{"resourceMetrics"', end)
    return bodies


def gauges(fakes: Path) -> list[tuple[str, str]]:
    found = []
    for body in reported(fakes):
        metric = body["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
        found.append((metric["name"], metric["gauge"]["dataPoints"][0]["asInt"]))
    return found


def queries(fakes: Path) -> list[str]:
    """The statements the scripts sent, each as one string, whatever its lines."""
    return [json.loads(line) for line in (fakes / "docker.stdin").read_text().splitlines()]


def test_a_backup_sends_its_statement_on_stdin_and_reports_success(fakes: Path) -> None:
    done = run("backup", environment(fakes), fakes)
    assert done.returncode == 0, done.stderr
    stamp = r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\dZ"
    credentials = (
        f"access_key_id = '{ACCESS}', secret_access_key = '{re.escape(SECRET)}', "
        f"session_token = '{re.escape(TOKEN)}'"
    )
    statement = (
        rf"BACKUP DATABASE default, DATABASE stackr_drill TO S3\(backups, 'clickhouse/{stamp}', "
        rf"{credentials}\) FORMAT Null"
    )
    assert any(re.fullmatch(statement, line) for line in queries(fakes))
    # The credentials are in a statement, never in a command line.
    argv = (fakes / "docker.argv").read_text()
    for secret in (SECRET, TOKEN, ACCESS):
        assert secret not in argv
    assert gauges(fakes) == [(METRICS["backup"], "1")]
    assert "http://10.40.128.10:9090/api/v1/otlp/v1/metrics" in (fakes / "curl.argv").read_text()


def test_a_failed_backup_reports_failure_and_leaks_nothing(fakes: Path) -> None:
    configure(fakes, fail_matching=["BACKUP"])
    done = run("backup", environment(fakes), fakes)
    assert done.returncode != 0
    assert "***" in done.stderr, "the client quotes the query: the credentials are taken out of it"
    for secret in (SECRET, TOKEN, ACCESS):
        assert secret not in done.stdout + done.stderr
    assert gauges(fakes) == [(METRICS["backup"], "0")]


def test_a_failure_before_any_credentials_scrubs_nothing_and_does_not_error(fakes: Path) -> None:
    """The first statements run before credentials exist: sed's empty pattern must not break."""
    configure(fakes, fail_matching=["CREATE DATABASE"])
    done = run("backup", environment(fakes), fakes)
    assert done.returncode != 0
    assert "sed:" not in done.stderr
    assert "CREATE DATABASE IF NOT EXISTS stackr_drill" in done.stderr


def test_credentials_that_could_carry_sql_are_refused(fakes: Path) -> None:
    done = run("backup", environment(fakes, AWS_SECRET_ACCESS_KEY="x'); DROP TABLE y; --"), fakes)
    assert done.returncode != 0
    assert "aren't what S3 gives out" in done.stderr
    assert not any("BACKUP" in line for line in queries(fakes)), "no backup was attempted"
    assert gauges(fakes) == [(METRICS["backup"], "0")]


def test_without_a_session_token_the_statement_has_none(fakes: Path) -> None:
    env = environment(fakes)
    del env["AWS_SESSION_TOKEN"]
    assert run("backup", env, fakes).returncode == 0
    assert "session_token" not in (fakes / "docker.stdin").read_text()


def imds_environment(fakes: Path, imds: str, **more: str) -> dict[str, str]:
    env = environment(fakes, IMDS_ENDPOINT=imds, STATE_BACKUP_CREDENTIALS="imds", **more)
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        del env[name]
    return env


def test_with_the_role_the_credentials_are_fetched_per_run(imds: str, fakes: Path) -> None:
    assert run("backup", imds_environment(fakes, imds), fakes).returncode == 0
    assert f"access_key_id = '{ACCESS}'" in (fakes / "docker.stdin").read_text()
    assert FakeIMDS.fetches == 1


def test_credentials_about_to_expire_are_waited_out_and_fetched_again(
    imds: str, fakes: Path
) -> None:
    """IMDS rotates credentials before they expire: a statement starts on the rotated ones."""
    FakeIMDS.lives = [2, 21600]
    env = imds_environment(
        fakes, imds, STATE_MIN_CREDENTIAL_SECONDS="100", STATE_CREDENTIAL_MARGIN="0"
    )
    done = run("backup", env, fakes)
    assert done.returncode == 0, done.stderr
    assert "waiting for IMDS to rotate them" in done.stderr
    assert FakeIMDS.fetches == 2
    backup = next(line for line in queries(fakes) if line.startswith("BACKUP"))
    assert f"access_key_id = '{ACCESS}1'" in backup, "the statement carries the rotated credentials"


def test_credentials_already_expired_stop_the_run_without_a_negative_sleep(
    imds: str, fakes: Path
) -> None:
    FakeIMDS.lives = [-600]
    done = run("backup", imds_environment(fakes, imds), fakes)
    assert done.returncode != 0
    assert "expire in -" in done.stderr
    assert "invalid option" not in done.stderr
    assert not any(line.startswith("BACKUP") for line in queries(fakes))
    assert FakeIMDS.fetches == 1, "nothing to wait for"


def test_credentials_that_are_still_short_after_rotating_stop_the_run(
    imds: str, fakes: Path
) -> None:
    FakeIMDS.lives = [2, 2]
    env = imds_environment(
        fakes, imds, STATE_MIN_CREDENTIAL_SECONDS="100", STATE_CREDENTIAL_MARGIN="0"
    )
    done = run("backup", env, fakes)
    assert done.returncode != 0
    assert "expire in" in done.stderr
    assert not any(line.startswith("BACKUP") for line in queries(fakes))
    assert gauges(fakes) == [(METRICS["backup"], "0")]


def test_the_drill_fetches_credentials_again_before_a_statement_that_would_outlast_them(
    imds: str, fakes: Path
) -> None:
    """The drill reaches the bucket four times, over up to two hours: each starts on enough."""
    FakeIMDS.lives = [104, 21600]
    configure(
        fakes,
        latest=STAMP,
        taken_age=3600,
        live_tables=["traces"],
        restored_tables=["traces"],
        delay_backup=5,
    )
    env = imds_environment(
        fakes, imds, STATE_MIN_CREDENTIAL_SECONDS="100", STATE_CREDENTIAL_MARGIN="0"
    )
    done = run("restore-drill", env, fakes)
    assert done.returncode == 0, done.stderr
    assert FakeIMDS.fetches == 2, "fetched once, and again when the delay left them under the floor"
    first = next(line for line in queries(fakes) if line.startswith("SELECT countIf(name >"))
    restore = next(line for line in queries(fakes) if line.startswith("RESTORE DATABASE default"))
    assert f"access_key_id = '{ACCESS}'" in first
    assert f"access_key_id = '{ACCESS}1'" in restore


def test_no_credential_is_in_any_process_s_arguments_while_a_statement_runs(fakes: Path) -> None:
    """sed outlives the statement it scrubs: its arguments, like docker's, must hold no secret."""
    configure(fakes, delay_backup=4)
    process = subprocess.Popen(
        [str(STATE_HOST / "backup")],
        env={"PATH": os.environ["PATH"], **environment(fakes)},
        cwd=fakes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        seen = ""
        for _ in range(40):
            time.sleep(0.2)
            seen = subprocess.run(
                ["ps", "-eo", "args"], capture_output=True, text=True, check=True
            ).stdout
            if "sed -f" in seen:
                break
        assert "sed -f /dev/fd/" in seen, "the scrub was running, and with a script by descriptor"
        for credential in (SECRET, TOKEN, ACCESS):
            assert credential not in seen
    finally:
        process.communicate(timeout=60)


def test_the_imds_session_token_is_not_in_curl_s_arguments(imds: str, tmp_path: Path) -> None:
    """curl is given the header by file descriptor; the fake IMDS shows it arrived all the same."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    real = shutil.which("curl")
    assert real is not None
    (fake_bin / "curl").write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >>"{tmp_path}/curl.argv"\nexec {real} "$@"\n'
    )
    (fake_bin / "curl").chmod(0o755)
    env = {"IMDS_ENDPOINT": imds, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
    assert run("imds-credentials", env, tmp_path).returncode == 0
    assert "a-session-token" not in (tmp_path / "curl.argv").read_text()
    assert any(line.startswith("GET") for line in FakeIMDS.log), "and the token was accepted"


def drill(fakes: Path, **config: Any) -> subprocess.CompletedProcess[str]:
    """The restore drill, against a ClickHouse that has the latest backup and these tables."""
    defaults: dict[str, Any] = {
        "latest": STAMP,
        "taken_age": 3600,
        "live_tables": ["spans", "traces"],
        "restored_tables": ["spans", "traces"],
    }
    configure(fakes, **{**defaults, **config})
    return run("restore-drill", environment(fakes), fakes)


def positions(fakes: Path, prefix: str) -> list[int]:
    return [index for index, line in enumerate(queries(fakes)) if line.startswith(prefix)]


def test_a_healthy_drill_restores_both_backups_and_drops_what_it_restored(fakes: Path) -> None:
    done = drill(fakes)
    assert done.returncode == 0, done.stderr
    assert gauges(fakes) == [(METRICS["restore-drill"], "1")]
    restores = positions(fakes, "RESTORE DATABASE")
    assert len(restores) == 2
    restored = [queries(fakes)[index] for index in restores]
    assert f"S3(backups, 'clickhouse/{STAMP}'" in restored[0]
    assert re.search(r"S3\(backups, 'drill/drill-\d{10}-\d{5}'", restored[1]), "a fixed-width name"
    drops = positions(fakes, "DROP DATABASE IF EXISTS")
    assert len(drops) == 4, "before the restores, and again when it ends"
    assert max(restores) < min(drops[2:]), (
        "the databases it restored are dropped after the restores"
    )


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"taken_age": 40 * 3600}, "is older than 36 hours"),
        ({"future": 2}, "2 of ClickHouse's backups are dated in the future"),
        ({"latest": ""}, "has no backup"),
        ({"used": 10_000, "free": 1_000}, "has no room to restore"),
        (
            {"live_tables": ["spans", "traces"], "restored_tables": ["traces"]},
            "has no rows in: spans",
        ),
        ({"sentinel_rows": 0}, "lacks the sentinel"),
        ({"restore_fails": True}, "Cannot restore"),
    ],
    ids=[
        "stale",
        "future-dated names",
        "none",
        "no room",
        "missing rows",
        "no sentinel",
        "restore fails",
    ],
)
def test_a_drill_that_finds_something_wrong_fails_says_why_and_still_cleans_up(
    fakes: Path, config: dict[str, Any], message: str
) -> None:
    done = drill(fakes, **config)
    assert done.returncode != 0
    assert message in done.stderr
    assert gauges(fakes) == [(METRICS["restore-drill"], "0")]
    for secret in (SECRET, TOKEN, ACCESS):
        assert secret not in done.stdout + done.stderr
    assert queries(fakes)[-2:] == [
        "DROP DATABASE IF EXISTS restore_drill SYNC",
        "DROP DATABASE IF EXISTS restore_sentinel SYNC",
    ], "the trap drops what it restored, whatever failed"


@pytest.mark.parametrize("config", [{"taken_age": 40 * 3600}, {"latest": ""}])
def test_a_drill_that_stops_at_the_latest_backup_restores_nothing(
    fakes: Path, config: dict[str, Any]
) -> None:
    assert drill(fakes, **config).returncode != 0
    assert not positions(fakes, "RESTORE"), "nothing was restored"
    assert not positions(fakes, "BACKUP"), "and no sentinel was backed up"


def test_a_drill_after_a_killed_one_drops_what_it_left_before_restoring(fakes: Path) -> None:
    done = drill(fakes, existing=["restore_drill", "restore_sentinel"])
    assert done.returncode == 0, done.stderr
    assert "already exists" not in done.stderr
    assert min(positions(fakes, "DROP DATABASE")) < min(positions(fakes, "RESTORE"))


def test_a_future_dated_name_fails_the_drill_but_the_real_latest_is_still_drilled(
    fakes: Path,
) -> None:
    done = drill(fakes, future=1)
    assert done.returncode != 0
    assert "1 backups are dated more than an hour in the future" in done.stderr
    assert "ok: ClickHouse's latest backup" in done.stderr, (
        "the real latest was restored and checked"
    )
    assert len(positions(fakes, "RESTORE DATABASE")) == 2
    assert gauges(fakes) == [(METRICS["restore-drill"], "0")]


def test_a_backup_dated_half_an_hour_ahead_is_within_the_tolerance(fakes: Path) -> None:
    assert drill(fakes, taken_age=-30 * 60).returncode == 0


def test_the_drill_compares_names_as_text_so_no_year_overflows(fakes: Path) -> None:
    """A name claiming year 9999 is past the cutoff as a string: it's never parsed as a time."""
    drill(fakes)
    names = next(line for line in queries(fakes) if line.startswith("SELECT countIf(name >"))
    assert "name > formatDateTime(toDateTime(" in names
    assert "name <= formatDateTime(toDateTime(" in names


def test_the_drill_ignores_names_that_are_not_a_timestamp_and_reads_times_as_utc(
    fakes: Path,
) -> None:
    drill(fakes)
    latest = next(line for line in queries(fakes) if line.startswith("SELECT countIf(name >"))
    assert "match(name, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z$')" in latest
    taken = next(line for line in queries(fakes) if line.startswith("SELECT toUnixTimestamp"))
    assert "'UTC'" in taken, "the server's time zone is not the backup's"


@pytest.mark.skipif(
    shutil.which("flock") is None, reason="flock is util-linux's, on the state host"
)
@pytest.mark.parametrize("script", ["backup", "restore-drill"])
def test_a_run_waits_for_the_one_holding_the_lock_and_then_gives_up(
    fakes: Path, script: str
) -> None:
    holder = subprocess.Popen(["flock", str(fakes / "lock"), "sleep", "30"])
    try:
        time.sleep(0.5)
        done = run(script, environment(fakes, STATE_LOCK_WAIT="1"), fakes)
    finally:
        holder.kill()
        holder.wait()
    assert done.returncode != 0
    assert "another backup or drill held the lock for 1 seconds" in done.stderr
    assert not (fakes / "docker.stdin").exists(), "nothing reached ClickHouse"
    assert gauges(fakes) == [(METRICS[script], "0")]


class Unit(configparser.ConfigParser):
    """A systemd unit, whose keys are case-sensitive and whose values have no interpolation."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def units() -> dict[str, Unit]:
    found = {}
    for path in sorted((STATE_HOST / "systemd").glob("*")):
        parser = Unit(interpolation=None, strict=False)
        parser.read_string(re.sub(r"^#.*$", "", path.read_text(), flags=re.M))
        found[path.name] = parser
    return found


def test_the_units_run_the_scripts_nightly_and_weekly_after_the_state_services() -> None:
    found = units()
    assert set(found) == {
        "stackr-state-backup.service",
        "stackr-state-backup.timer",
        "stackr-state-restore-drill.service",
        "stackr-state-restore-drill.timer",
    }
    for name in ("backup", "restore-drill"):
        service = found[f"stackr-state-{name}.service"]
        assert service["Service"]["Type"] == "oneshot"
        # Wants, not Requires: restarting stackr-state, as rotating a secret does, must not
        # stop a run that is going.
        assert service["Unit"]["Wants"] == "stackr-state.service"
        assert "Requires" not in service["Unit"]
        assert "stackr-state.service" in service["Unit"]["After"]
        start = service["Service"]["ExecStart"].replace("@STACKR_DIR@", "").removeprefix("/")
        assert start == f"deploy/aws/state-host/{name}"
        assert os.access(STATE_HOST / name, os.X_OK), f"{name} is executable"
        assert "Persistent" in found[f"stackr-state-{name}.timer"]["Timer"]
    assert found["stackr-state-backup.timer"]["Timer"]["OnCalendar"] == "*-*-* 03:00:00 UTC"
    drill_timer = found["stackr-state-restore-drill.timer"]["Timer"]
    assert drill_timer["OnCalendar"] == "Sun *-*-* 05:00:00 UTC"
    drill_service = found["stackr-state-restore-drill.service"]
    assert "stackr-state-backup.service" in drill_service["Unit"]["After"]
    for timer in ("backup", "restore-drill"):
        assert found[f"stackr-state-{timer}.timer"]["Install"]["WantedBy"] == "timers.target"


def test_the_units_read_only_the_prometheus_url_and_are_hardened_where_docker_allows() -> None:
    for name in ("backup", "restore-drill"):
        service = units()[f"stackr-state-{name}.service"]["Service"]
        assert service["EnvironmentFile"] == "/run/stackr/backup.env", "not ClickHouse's passwords"
        for setting in ("NoNewPrivileges", "PrivateTmp", "ProtectHome"):
            assert service[setting] == "true"


def test_every_script_is_a_bash_script_and_the_library_names_the_credentials_helper() -> None:
    for name in ("backup", "restore-drill", "imds-credentials", "lib"):
        assert (STATE_HOST / name).read_text().startswith("#!/usr/bin/env bash")
    assert '"$here/imds-credentials"' in (STATE_HOST / "lib").read_text()
