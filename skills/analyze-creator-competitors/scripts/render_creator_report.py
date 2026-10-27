#!/usr/bin/env python3
"""Render a concise Creator-facing view from CompetitorResearchReport V3."""

from __future__ import annotations

import argparse
import json
import re
import math
import statistics
from pathlib import Path
from typing import Any
import sys

# Sibling imports must not leave a __pycache__ in the signed, checksummed skill directory.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_basis import basis_sentence, shown_multiple_sample_sizes  # noqa: E402

ZERO_SAMPLES = "Selected accounts not compared for content performance (0 analyzable posts in the requested window): {refs}."


MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]*\]\([^\)\n]*\)")
NESTED_MARKDOWN_LINK_RE = re.compile(
    r"\[[^\]\n]*\[[^\]\n]*\]\([^\)\n]*\)[^\]\n]*\]\([^\)\n]*\)"
)


def content_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["content_id"]: item for item in report.get("top_content") or []}


def display_title(value: str) -> str:
    first = (value or "").strip().splitlines()[0].strip()
    return first[:72] + ("…" if len(first) > 72 else "")


# Fixed labels exist once, in English. Model-written prose (titles, mechanisms, gaps) stays in the
# Creator's language; the host relays these labels in that language.
LABELS = {
    "roster": "Accounts in this comparison",
    "direct": "direct",
    "adjacent": "adjacent",
    "media": "media",
    "unspecified": "unclassified",
    "adjacent_evidence": "Adjacent evidence:",
    "media_evidence": "Media evidence:",
    "differentiation": "Your differentiation:",
    "gaps": "What's missing",
    "next_step": "Next step",
    "not_compared": "Requested accounts not compared (no verified public evidence; no substitute was used): {refs}.",
}
RELATIONSHIPS = ("direct", "adjacent", "media", "unspecified")
SEPARATOR = ", "
PROOF_SEPARATOR = "; "
SENTENCE_TERMINATORS = ".!?\u3002\uff01\uff1f\u2026"


def end_sentence(value: str) -> str:
    """Close model prose once, keeping its own terminal mark in any script."""
    text = str(value).rstrip().rstrip("\uff1b;\uff0c,\u3001 ")
    if text and text[-1] in SENTENCE_TERMINATORS:
        return text
    return text + "."


def proof_links(refs: list[str], content: dict[str, dict[str, Any]], separator: str = SEPARATOR) -> str:
    values = []
    for ref in refs[:2]:
        item = content.get(ref)
        if item:
            title = display_title(str(item.get("title") or item["account_ref"]))
            values.append(f"[{title}]({item['url']})")
    return separator.join(values)


def select_pattern_evidence(
    pattern: dict[str, Any],
    report: dict[str, Any],
    content: dict[str, dict[str, Any]],
) -> list[tuple[str, str]]:
    """Choose two strong proof points, preferring distinct accounts."""
    outliers = {
        str(item.get("content_id")): item
        for item in report.get("outliers") or []
        if item.get("content_id") is not None and item.get("ratio") is not None
    }
    proof_points = pattern.get("proof_points") or []
    report_scores: list[float] = []
    for report_item in content.values():
        report_views = (report_item.get("metrics") or {}).get("views")
        if not isinstance(report_views, (int, float)) or isinstance(report_views, bool):
            continue
        report_score = math.log1p(float(report_views))
        report_outlier = outliers.get(str(report_item.get("content_id")))
        if report_outlier:
            report_ratio = float(report_outlier["ratio"])
            report_n = int((report_outlier.get("baseline") or {}).get("sample_size") or 0)
            report_support = math.sqrt(report_n / (report_n + 5)) if report_n > 0 else 0.0
            report_score += math.log(report_ratio) * report_support
        report_scores.append(report_score)
    evidence_floor = statistics.median(report_scores) if len(report_scores) >= 4 else float("-inf")
    candidates = []
    for index, ref in enumerate(pattern.get("content_refs") or []):
        item = content.get(str(ref))
        if not item or index >= len(proof_points):
            continue
        outlier = outliers.get(str(ref))
        metrics = item.get("metrics") or {}
        views = metrics.get("views")
        evidence_score = math.log1p(float(views)) if isinstance(views, (int, float)) and not isinstance(views, bool) else 0.0
        if outlier:
            ratio = float(outlier["ratio"])
            sample_size = int((outlier.get("baseline") or {}).get("sample_size") or 0)
            sample_support = math.sqrt(sample_size / (sample_size + 5)) if sample_size > 0 else 0.0
            evidence_score += math.log(ratio) * sample_support
        candidates.append({
            "index": index,
            "ref": str(ref),
            "proof": str(proof_points[index]),
            "account_ref": str(item.get("account_ref") or ""),
            "ratio": float(outlier["ratio"]) if outlier else None,
            "evidence_score": evidence_score,
            "views": views,
            "likes": metrics.get("likes"),
            "comments": metrics.get("comments"),
        })
    candidates.sort(
        key=lambda item: (
            item["evidence_score"],
            item["views"] is not None,
            item["views"] if item["views"] is not None else float("-inf"),
            item["likes"] is not None,
            item["likes"] if item["likes"] is not None else float("-inf"),
            item["comments"] is not None,
            item["comments"] if item["comments"] is not None else float("-inf"),
            -item["index"],
        ),
        reverse=True,
    )
    if not candidates:
        return []
    strong_candidates = [item for item in candidates if item["evidence_score"] > evidence_floor]
    if strong_candidates:
        candidates = strong_candidates
    elif evidence_floor != float("-inf"):
        candidates = candidates[:1]
    selected = [candidates[0]]
    different_account = next(
        (item for item in candidates[1:] if item["account_ref"] != candidates[0]["account_ref"]),
        None,
    )
    if different_account:
        selected.append(different_account)
    elif len(candidates) > 1:
        selected.append(candidates[1])
    return [(item["ref"], item["proof"]) for item in selected]


def mask_protected(text: str, report: dict[str, Any]) -> tuple[str, list[str]]:
    protected: list[str] = []

    def mask(value: str) -> str:
        token = f"\x00KABO_PROTECTED_{len(protected)}\x00"
        protected.append(value)
        return token

    result = MARKDOWN_LINK_RE.sub(lambda match: mask(match.group(0)), text)
    titles = {
        str(item.get("title") or "")
        for item in report.get("top_content") or []
        if str(item.get("title") or "")
    }
    for title in sorted(titles, key=len, reverse=True):
        result = re.sub(re.escape(title), lambda match: mask(match.group(0)), result)
    return result, protected


def restore_protected(text: str, protected: list[str]) -> str:
    result = text
    for index, value in enumerate(protected):
        result = result.replace(f"\x00KABO_PROTECTED_{index}\x00", value)
    return result


def link_accounts(text: str, report: dict[str, Any]) -> str:
    result, protected = mask_protected(text, report)
    competitors = sorted(report.get("competitors") or [], key=lambda item: len(str(item.get("handle") or "")), reverse=True)
    for item in competitors:
        clean = str(item.get("handle") or "").lstrip("@")
        platform = str(item.get("platform") or "")
        label = clean if platform == "youtube" else "@" + clean
        url = str(item.get("url") or "")
        if not clean or not url:
            continue
        candidates = ["@" + clean, clean] if platform == "youtube" else [label]
        # A handle must end where the name ends: @name1 never links inside @name10 or @name.shop.
        pattern = "(?:" + "|".join(re.escape(candidate) for candidate in sorted(candidates, key=len, reverse=True)) \
            + r")(?![\w-]|\.\w)"

        def link_first(_: re.Match[str]) -> str:
            token = f"\x00KABO_PROTECTED_{len(protected)}\x00"
            protected.append(f"[{label}]({url})")
            return token

        result = re.sub(pattern, link_first, result, count=1)
    return restore_protected(result, protected)


def validate_rendered_markdown(markdown: str, report: dict[str, Any]) -> None:
    content = content_map(report)
    expected_titles = set()
    for pattern in report.get("patterns") or []:
        for ref, proof in select_pattern_evidence(pattern, report, content):
            title = str((content.get(ref) or {}).get("title") or "")
            if title and title in proof:
                expected_titles.add(title)
    missing_titles = sorted(title for title in expected_titles if title not in markdown)
    if missing_titles:
        raise ValueError(f"rendered report changed source title: {missing_titles[0]}")
    if NESTED_MARKDOWN_LINK_RE.search(markdown):
        raise ValueError("rendered report contains a nested Markdown link")


def render_gap_section(report: dict[str, Any], content: dict[str, dict[str, Any]]) -> list[str]:
    gaps = [item for item in report.get("gaps") or [] if isinstance(item, dict) and item.get("summary")]
    if not gaps:
        return []
    lines = [f"## {LABELS['gaps']}", ""]
    for gap in gaps[:4]:
        refs = proof_links(list(gap.get("content_refs") or [])[:2], content)
        summary = end_sentence(gap["summary"])
        if refs:
            summary += f" ({refs})"
        lines += [link_accounts(summary, report), ""]
    return lines


def roster_section(report: dict[str, Any]) -> list[str]:
    """Surface comparable accounts before mechanisms; known empty accounts get a separate notice.

    One live run kept six accounts through selection, then the Creator-facing
    report named only one handle because the renderer never printed the roster.
    """
    competitors = [item for item in report.get("competitors") or [] if not zero_sample(item)]
    if not competitors:
        return []
    lines = [f"## {LABELS['roster']}", ""]
    for item in competitors:
        handle = str(item.get("handle") or "").lstrip("@")
        platform = str(item.get("platform") or "")
        label = handle if platform == "youtube" else "@" + handle
        raw_relationship = str(item.get("relationship") or "")
        relationship = LABELS[raw_relationship] if raw_relationship in RELATIONSHIPS else raw_relationship
        summary = str(item.get("summary") or "").strip()
        row = f"- {label} ({relationship}) {summary}" if summary else f"- {label} ({relationship})"
        lines.append(link_accounts(row, report))
    lines.append("")
    return lines


def zero_sample(item: dict[str, Any]) -> bool:
    return type(item.get("sample_size")) is int and item["sample_size"] == 0


def zero_sample_refs(report: dict[str, Any]) -> list[str]:
    refs = []
    for item in report.get("competitors") or []:
        handle = str(item.get("handle") or "").lstrip("@")
        if zero_sample(item) and handle:
            ref = handle if item.get("platform") == "youtube" else "@" + handle
            if ref not in refs:
                refs.append(ref)
    return refs


def comparison_basis(report: dict[str, Any]) -> dict[str, Any]:
    """Use known nonempty account samples for the view, without changing the validated Report."""
    competitors = report.get("competitors") or []
    if not competitors:
        return report
    sizes = [item.get("sample_size") for item in competitors]
    coverage = dict(report.get("coverage") or {})
    if all(type(size) is int and size >= 0 for size in sizes):
        coverage["competitor_count"] = sum(size > 0 for size in sizes)
    elif any(zero_sample(item) for item in competitors):
        # A zero is known, but the rest are not: omit an exact population claim, never invent it.
        coverage.pop("competitor_count", None)
    else:
        return report  # Older Reports without per-account sample sizes retain their existing basis.
    return {**report, "coverage": coverage}


def render(report: dict[str, Any]) -> str:
    overview = report["overview"]
    content = content_map(report)
    relationships = {
        str(item.get("account_ref")): str(item.get("relationship") or "")
        for item in report.get("competitors") or []
    }
    lines = [f"# {link_accounts(overview['title'], report)}", ""]
    lines += roster_section(report)
    empty = zero_sample_refs(report)
    if empty:
        lines += [link_accounts(ZERO_SAMPLES.format(refs=", ".join(empty)), report), ""]
    lines += [link_accounts(overview["summary"], report), ""]
    cited: list[str] = []
    for pattern in report.get("patterns", [])[:3]:
        selected = select_pattern_evidence(pattern, report, content)
        cited += [ref for ref, _ in selected]
        refs = proof_links([ref for ref, _ in selected], content)
        mechanism = end_sentence(pattern["mechanism"])
        proof = PROOF_SEPARATOR.join(value.rstrip("\u3002\uff1b;. ") for _, value in selected)
        selected_relationships = {
            relationships.get(str(content[ref].get("account_ref")))
            for ref, _ in selected if ref in content
        }
        evidence_label = ""
        if selected_relationships and "direct" not in selected_relationships:
            evidence_label = LABELS["adjacent_evidence" if "adjacent" in selected_relationships else "media_evidence"] + " "
        paragraph = mechanism + (" " + evidence_label + link_accounts(proof, report) + "." if proof else "")
        lines += [
            f"## {pattern['pattern']}", "",
            paragraph + (f" ({refs})" if refs else ""), "",
            f"**{LABELS['differentiation']}** {pattern['differentiation']}", "",
        ]
    lines += render_gap_section(report, content)
    next_action = str(overview.get("next_action") or "").strip()
    if next_action:
        lines += [f"## {LABELS['next_step']}", "", next_action]
    markdown = "\n".join(lines).strip() + "\n"
    validate_rendered_markdown(markdown, report)
    # One fixed sentence of measurement basis; the rest stays in the Report for follow-up questions.
    missing = [str(ref) for ref in (report.get("coverage") or {}).get("requested_not_compared") or []]
    if missing:
        markdown += "\n" + LABELS["not_compared"].format(refs=", ".join(missing)) + "\n"
    basis = basis_sentence(comparison_basis(report), shown_multiple_sample_sizes(report, cited))
    return markdown + (f"\n*{basis}*\n" if basis else "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(report), encoding="utf-8")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
