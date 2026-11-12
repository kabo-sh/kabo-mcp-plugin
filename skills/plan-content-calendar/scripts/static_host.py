#!/usr/bin/env python3
"""Reserve one local run directory per request for this Skill; no network or model loop."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parent.parent
# This Skill calls no /mcp-pub data tools and has no tool results to stage, so only init is kept;
# the directory layout stays consistent with other Skills' init, making runs easy to recognise in the same workspace.


def init(workspace):
    base = Path(workspace).resolve(strict=True) / ".kabo-runs"
    if SKILL == base or SKILL in base.parents:
        raise ValueError("Runs must be outside the installed Skill")
    base.mkdir(mode=0o700, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(6)
    run = base / name
    run.mkdir(mode=0o700)
    for name in ("snapshot", "analysis", "report", "owner"):
        (run / name).mkdir(mode=0o700)
    (run / "snapshot/.host-evidence").mkdir(mode=0o700)
    write_new(run / ".static-run.json", json.dumps({"format": "kabo.static-run.v1", "skill": SKILL.name}).encode())
    return run


def write_new(path, body):
    # Exclusive write: retries and concurrency must not overwrite existing evidence.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("--workspace", required=True)
    args = parser.parse_args()
    print(init(args.workspace))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print("Static run operation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
