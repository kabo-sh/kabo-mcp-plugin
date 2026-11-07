#!/usr/bin/env python3
"""Check that a reply retains the validated account report before it is sent."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def semantic_strings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"headline", "diagnosis", "pattern", "explanation", "action", "success_metric",
                       "data_gaps", "biography", "display_name"}:
                yield from strings(child)
            else:
                yield from semantic_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from semantic_strings(child)


def delivery_issues(markdown: str, report: dict, reply: str) -> list[str]:
    source, target = normalized(markdown), normalized(reply)
    # 只检查确实渲染进正文的语义字符串；未显示的内部字段不要求用户看到。
    required = sorted({normalized(s) for s in semantic_strings(report)
                       if normalized(s) and normalized(s) in source})
    issues = ["Missing or rewritten report text: " + s for s in required if s not in target]
    # 固定标签允许翻译，但引用与数字不能借翻译而省略或改写。
    links = lambda text: Counter(re.findall(r"\]\((https?://[^\s)]+)\)", text))
    for url, count in (links(markdown) - links(reply)).items():
        issues.append(f"Missing cited example ({count} occurrence(s)): {url}")
    for label in re.findall(r"\[([^\]]+)\]\(https?://[^\s)]+\)", markdown):
        if normalized(label) not in target:
            issues.append("Missing or rewritten quoted source title: " + label)
    numbers = lambda text: Counter(re.findall(r"(?<![\w])\d+(?:[.,]\d+)*(?:%|[KMBx])?", text))
    for number, count in (numbers(markdown) - numbers(reply)).items():
        issues.append(f"Missing or changed displayed number ({count} occurrence(s)): {number}")
    # 主体段落不能整体消失；固定标签可翻译，但既有语义句与引文须先通过以上检查。
    headings = lambda text: sum(bool(re.match(r"^#{1,6}\s+\S", line)) for line in text.splitlines())
    if headings(reply) < headings(markdown):
        issues.append("Missing report sections: retain every heading in order (fixed labels may be translated).")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--reply-file", required=True, help="UTF-8 draft file, or - for stdin")
    args = parser.parse_args()
    try:
        markdown = (args.report_dir / "ACCOUNT_REVIEW.md").read_text(encoding="utf-8")
        report = json.loads((args.report_dir / "account_review.json").read_text(encoding="utf-8"))
        reply = sys.stdin.read() if args.reply_file == "-" else Path(args.reply_file).read_text(encoding="utf-8")
        if not isinstance(report, dict) or report.get("schema_version") != "account-review-report.v3":
            raise ValueError("expected the composed account-review-report.v3 report")
        issues = delivery_issues(markdown, report, reply)
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 2
    if issues:
        print(json.dumps({"status": "needs_revision", "issues": issues,
                          "next_action": "Restore the omitted report content in this reply draft only and check again. Do not edit the validated report or run another review."}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ready_to_send", "reply_sha256": hashlib.sha256(reply.encode()).hexdigest(),
                      "next_action": "Send this entire checked draft unchanged now. Do not compose a shorter answer. This checks delivery completeness, not the truth of new claims."}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
