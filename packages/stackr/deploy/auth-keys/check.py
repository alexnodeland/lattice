"""auth-keys against a stubbed Secrets Manager, in its own image, which deploy/build-images mounts
it into.

Four cases: nothing written yet; both written and verifying; a service role's key that no longer
verifies; and a run that loses the race to write the key set. Then a refusal, which it reports by
its code alone.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import sys

import boto3
from botocore.stub import ANY, Stubber

sys.path.insert(0, "/app")
loader = importlib.machinery.SourceFileLoader("auth_keys_script", "/app/auth-keys")
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
script = importlib.util.module_from_spec(spec)
loader.exec_module(script)

KEYS = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/auth-jwt-keys-AAAAAA"
ROLE = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/auth-service-role-key-AAAAAA"
os.environ.update(
    AUTH_JWT_KEYS_ARN=KEYS,
    AUTH_SERVICE_ROLE_KEY_ARN=ROLE,
    AWS_DEFAULT_REGION="us-east-1",
    AWS_ACCESS_KEY_ID="check",
    AWS_SECRET_ACCESS_KEY="check",
)
failures = 0


def run(case: str, expected: int, script_of_calls) -> None:
    """Runs auth-keys against a client that answers exactly the calls given, in order."""
    global failures
    client = boto3.client("secretsmanager")
    stubber = Stubber(client)
    script_of_calls(stubber)
    script.boto3.client = lambda *_args, **_kwargs: client
    errors = io.StringIO()
    with stubber, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
        try:
            code = script.main()
            stubber.assert_no_pending_responses()
        except Exception as error:  # a failed case is reported, not raised
            code = f"{type(error).__name__}: {error}"
    if code == expected and "Traceback" not in errors.getvalue():
        print(f"ok: auth-keys, {case}")
    else:
        print(f"FAIL: auth-keys, {case}: {code!r} {errors.getvalue()}", file=sys.stderr)
        failures += 1


def value(arn: str, secret: str | None) -> tuple[str, dict, dict]:
    response = {"ARN": arn, "Name": arn.rsplit(":", 1)[1]}
    if secret is not None:
        response["SecretString"] = secret
    return "get_secret_value", response, {"SecretId": arn}


def put(arn: str) -> tuple[str, dict, dict]:
    response = {"ARN": arn, "Name": arn.rsplit(":", 1)[1]}
    return (
        "put_secret_value",
        response,
        {"SecretId": arn, "SecretString": ANY, "ClientRequestToken": ANY},
    )


keys = script.key_set()
role = script.service_role_key(keys)
other = script.service_role_key(script.key_set())


def fresh(stubber: Stubber) -> None:
    stubber.add_response(*value(KEYS, None))
    stubber.add_response(*put(KEYS))
    stubber.add_response(*value(KEYS, keys))
    stubber.add_client_error(
        "get_secret_value", "ResourceNotFoundException", expected_params={"SecretId": ROLE}
    )
    stubber.add_response(*put(ROLE))
    stubber.add_response(*value(ROLE, role))


def written(stubber: Stubber) -> None:
    stubber.add_response(*value(KEYS, keys))
    stubber.add_response(*value(ROLE, role))


def stale(stubber: Stubber) -> None:
    stubber.add_response(*value(KEYS, keys))
    stubber.add_response(*value(ROLE, other))
    stubber.add_response(*put(ROLE))
    stubber.add_response(*value(ROLE, role))


def raced(stubber: Stubber) -> None:
    stubber.add_response(*value(KEYS, None))
    stubber.add_client_error(
        "put_secret_value",
        "ResourceExistsException",
        expected_params={"SecretId": KEYS, "SecretString": ANY, "ClientRequestToken": ANY},
    )
    stubber.add_response(*value(KEYS, keys))
    stubber.add_response(*value(ROLE, role))


def refused(stubber: Stubber) -> None:
    stubber.add_client_error(
        "get_secret_value", "AccessDeniedException", expected_params={"SecretId": KEYS}
    )


run("with nothing written yet, writes both", 0, fresh)
run("with both written and verifying, writes nothing", 0, written)
run("with a service role's key that no longer verifies, writes it again", 0, stale)
run("losing the race to write the key set, keeps the winner's", 0, raced)
run("refused, says so without a traceback", 1, refused)
sys.exit(1 if failures else 0)
