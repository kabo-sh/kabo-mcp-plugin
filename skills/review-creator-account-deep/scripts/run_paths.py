#!/usr/bin/env python3
"""Find a file this Skill's steps name, wherever the run directory actually keeps it.

Every step here starts from `account_analysis.json`, which `review-creator-account` leaves in the
run directory. The steps name it relatively, and a model that types one wrong prefix gets a bare
"no such file" — then goes looking. Observed 2026-09-22 on @vinny_creative: the command ran with
`output/account_analysis.json`, failed, and the run answered by searching the tree with `rg`; the
one turn that followed carried 2.4 MB of shell output and the request came back 413 Payload Too
Large, after ten videos had already been watched. Locating the file is settled work, so it stops
being the model's to get right.

Resolution never leaves this run: only the run directory and the few folders it reserves.
"""

from __future__ import annotations

import re
from pathlib import Path

RUN_DIR = re.compile(r"^(\d{8}T\d{6})Z-[0-9a-f]+$")
# Where a step's inputs and outputs live inside a reserved run directory.
SEARCHED = ("", "output", "analysis", "owner", "report")


def run_directory(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if RUN_DIR.match(candidate.name):
            return candidate
    return None


def resolve_input(given: Path) -> Path:
    """`given` when it exists, else the same file name inside this run's own folders.

    Raises when the file is nowhere in the run: a missing catalog Review has to stop the step,
    and that message is already what the caller prints.
    """
    if given.exists():
        return given
    run = run_directory()
    if run is not None:
        for folder in SEARCHED:
            candidate = run / folder / given.name if folder else run / given.name
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(
        f"{given} does not exist, and no {given.name} was found in this run directory. "
        "The catalog Review has to run first; do not search the filesystem for it."
    )
