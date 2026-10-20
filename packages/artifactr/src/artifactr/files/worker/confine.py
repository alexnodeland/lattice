"""Sets a CLI's limits, then becomes it: the launcher the worker starts every CLI under.

Run by path, as `python -I confine.py --cpu S --memory B --files B -- CLI ARGS...`, so it imports
the standard library alone and adds nothing to a call's start but the interpreter's. The limits
are the kernel's, by `setrlimit`, and outlive the `exec`: CPU seconds, past which the CLI is
killed; its address space, past which it can't allocate; and the largest file it may write, past
which a write fails. Each ends the CLI mid-call, which `Spawn` reports as `crashed`. macOS refuses
a limit on the address space, and enforces none, so there the CLI is started without one; the
worker's image is Linux.
"""

import argparse
import os
import resource
import sys


def main() -> None:
    """Set the limits the arguments name, and replace this process with the CLI they end with."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--memory", type=int, required=True)
    parser.add_argument("--files", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no CLI to start")
    limits = [(resource.RLIMIT_CPU, args.cpu), (resource.RLIMIT_FSIZE, args.files)]
    if sys.platform != "darwin":
        limits.append((resource.RLIMIT_AS, args.memory))
    for limit, value in limits:
        resource.setrlimit(limit, (value, value))
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
