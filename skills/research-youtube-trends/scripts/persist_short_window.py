#!/usr/bin/env python3
"""Place one short-window response from this run's staged tool results, without any-status."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import persist_envelope as records


def place(*, dest=None, into=None, at=None, connector_id, operation, handle=None):
    """Place one short-window response exactly as persist_envelope.py does with these arguments."""
    if (dest is None) == (into is None):
        raise ValueError("give exactly one of --dest or --into")
    return records.persist(dest, into=into, at=at, connector_id=connector_id, operation=operation, handle=handle)


def main():
    """Expose only the short-window placement arguments, never any-status."""
    parser = argparse.ArgumentParser(description=__doc__)
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument("--dest", type=Path)
    outputs.add_argument("--into", type=Path)
    parser.add_argument("--at", action="append")
    parser.add_argument("--connector", dest="connector_id", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--handle")
    args = parser.parse_args()
    try:
        result = place(**vars(args))
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
