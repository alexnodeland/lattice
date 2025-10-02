#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastapi[standard]>=0.115.12",
# ]
# ///
"""Development server runner for artifactr."""

import subprocess
import sys


def main():
    """Run the development server."""
    sys.exit(subprocess.call(["uvicorn", "src.artifactr.main:app", "--reload"]))


if __name__ == "__main__":
    main()
