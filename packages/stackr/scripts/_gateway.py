"""The LLM gateway's (LiteLLM proxy's) admin API, called with the master key, for the scripts that
provision it: create-tenant and create-portal-key."""

import json
import urllib.error
import urllib.request
from typing import Any


class Gateway:
    """The proxy's admin API, called with the master key.

    Args:
        base_url: Where the proxy is.
        master_key: Its master key.
        script: The script's name, which its exit messages begin with.
    """

    def __init__(self, base_url: str, master_key: str, script: str) -> None:
        self.base_url = base_url
        self.master_key = master_key
        self.script = script

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        """Send one request; return the decoded JSON, or raise HTTPError.

        Exits when the gateway can't be reached, doesn't answer in time or drops the connection.
        """
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.master_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError:
            raise
        except OSError as error:
            # A URLError while connecting; a TimeoutError or a dropped connection while waiting
            # for the answer.
            reason = getattr(error, "reason", error)
            raise SystemExit(f"{self.script}: the gateway at {self.base_url}: {reason}") from error


def error_message(error: urllib.error.HTTPError) -> str:
    """The proxy's error message, for an HTTP error (which it closes)."""
    with error:
        try:
            return str(json.loads(error.read())["error"]["message"])
        except (ValueError, KeyError, TypeError):
            return f"HTTP {error.code}"
