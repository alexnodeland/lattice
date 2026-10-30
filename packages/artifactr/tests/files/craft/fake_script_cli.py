"""A stand-in for a CLI that runs a script on a call: what the call's `do` says, it does.

Run as `python -I fake_script_cli.py [ARGUMENTS...] SCRIPT --pass CALL`. It writes its result
beside the call, as a script does: `echo`, the call, its arguments and its environment; `write`,
a file in `out/` of `size` bytes; `linger`, a process left behind in its group, its id in
`out/lingering`; `refuse`; `other`, a result from another version; `crash`, no result; `flood`,
no result after printing more than the adapter keeps, and exit status 3; `segfault`, no result,
killed by SIGSEGV; `hang`, never ending.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    called = Path(sys.argv[sys.argv.index("--pass") + 1])
    here = called.parent
    call = json.loads(called.read_text())
    result: dict[str, object] = {"version": "1.0.0", "result": None}
    match call["do"]:
        case "echo":
            source = here / "in" / "document.txt"
            result["result"] = {
                "arguments": sys.argv[1:-2],
                "home": os.environ["HOME"] == str(here),
                "environment": sorted(os.environ),
                "source": source.read_text() if source.exists() else None,
            }
        case "write":
            (here / "out" / "saved.txt").write_bytes(b"x" * call["size"])
        case "linger":
            lingering = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            (here / "out" / "lingering").write_text(str(lingering.pid))
        case "refuse":
            result["refused"] = "no such command"
        case "other":
            result["version"] = "0.9.0"
        case "crash":
            sys.stderr.write("it ended\n")
            return
        case "flood":
            sys.stdout.write("the first line\n" + "noise\n" * 2000)
            sys.stdout.flush()
            sys.stderr.write("the cause, last\n")
            sys.exit(3)
        case "segfault":
            os.kill(os.getpid(), signal.SIGSEGV)
        case _:
            time.sleep(60)
    (here / "result.json").write_text(json.dumps(result))


main()
