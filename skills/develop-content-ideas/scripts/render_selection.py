#!/usr/bin/env python3
"""Render a brief selection with the original displayed numbers and titles."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from deliver_ideas import atomic_write, digest


def render(source: str, selection: list) -> str:
    # 原始报告的编号是唯一标识，不能把精选列表再排成新的1、2、3。
    entries = re.findall(r"^### ([1-9][0-9]*)\. (.+)$", source, re.M)
    by_number = {int(number): title for number, title in entries}
    if not entries or len(by_number) != len(entries):
        raise ValueError("Use one exact previously delivered list, with unique original numbered headings.")
    if not isinstance(selection, list) or not selection:
        raise ValueError("selection must be a nonempty array of number/summary objects")
    seen, lines = set(), []
    for item in selection:
        if not isinstance(item, dict) or set(item) != {"number", "summary"}:
            raise ValueError("Each selection requires exactly number and summary; titles come from the source.")
        number, summary = item["number"], item["summary"]
        if type(number) is not int or number not in by_number or number in seen:
            raise ValueError("Select distinct original numbers present in the source list.")
        if not isinstance(summary, str) or not summary.strip() or "\n" in summary or "\r" in summary:
            raise ValueError("Each summary must be one nonempty paragraph grounded in the selected source entry.")
        seen.add(number)
        lines.append(f"- **#{number} {by_number[number]}** — {summary.strip()}")
    return "\n\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        if output in {args.source.resolve(), args.selection.resolve()}:
            raise ValueError("Output must not overwrite the source or selection input.")
        output.unlink(missing_ok=True)
        source = args.source.read_bytes()
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        text = render(source.decode("utf-8"), selection)
        atomic_write(output, text.encode("utf-8"))
        print(json.dumps({"status": "selection_rendered", "report_path": str(output),
                          "source_sha256": digest(source), "report_sha256": digest(text.encode("utf-8")),
                          "original_numbers": [item["number"] for item in selection],
                          "semantic_summary_validation": "author_must_check_against_source"}))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "not_deliverable", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
