#!/usr/bin/env python3
"""Render concise and full Markdown reports from ScriptPackage JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from script_duration import estimate


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def markdown_quote(value: str) -> list[str]:
    """Preserve paragraph and line breaks inside one Markdown blockquote."""
    return [f"> {line}" if line else ">" for line in value.splitlines() or [""]]


def validate_concise(markdown: str, data: dict) -> None:
    """Reject a Creator-facing projection that hides a production boundary."""
    required = [data["status"], data["overview"].get("key_gap") or ""]
    required.extend(
        item["question"]
        for item in (data.get("interaction") or {}).get("required_questions") or []
    )
    packaging = data.get("packaging") or {}
    required.extend(
        line for line in str(packaging.get("caption_or_description") or "").splitlines() if line
    )
    missing = [value for value in required if value and value not in markdown]
    if missing:
        raise ValueError(f"Creator-facing script package dropped material boundaries: {missing}")


def duration_lines(data):
    """Render one stable timing basis; the host localizes it for the creator."""
    result = estimate(data)
    if result is None:
        return []
    words = ('Duration estimate (not a timed read-through)', 'speech', 'demonstration', 'target', 'mean', 'median', 'current explicit duration', 'applicable prior duration', 'comparable channel sample and content estimate', 'platform-form and content estimate; no channel sample')
    title, speech, demo, target, mean, median, *bases = words
    lines = [f"{title}: ≈{result['estimated_seconds']}s; {speech} ≈{result['spoken_seconds']}s; {demo} {result['non_speaking_seconds']}s.", '']
    plan = data.get('input_snapshot', {}).get('duration_plan', {}).get('decision')
    if plan:
        basis_keys = ['explicit_current_request', 'applicable_prior_request', 'comparable_channel_and_content_estimate', 'platform_form_and_content_estimate']
        basis = bases[basis_keys.index(plan['basis'])]
        line = f"{target}: {plan['target_seconds']}s ({plan['range_seconds'][0]}–{plan['range_seconds'][1]}s); {basis}"
        stats = plan['statistics']
        if stats:
            line += f"; n={stats['n']}, {mean}={stats['mean_seconds']}s, {median}={stats['median_seconds']}s, {stats['window_start']}–{stats['window_end']}"
        lines += [line, '']
    return lines


# The labels this file adds around the package's own content. One set, in English.
#
# They used to be Chinese, hard-coded, with no alternative set: the status line, every section
# heading and the scene table's column headers stayed Chinese over a creator's own English
# script, while `duration_lines()` above had already moved to English, so the document came out
# mixed. Nothing here is the package's content — the headline, scenes, hooks and caption arrive
# already written in the creator's language because the model wrote them there. These are this
# renderer's own connective tissue, and the main agent restates them when it presents the report.

def concise(data: dict) -> str:
    """Render the concise creator report from a validated package."""
    lines = [
        "# Script & Packaging",
        "",
        f"> {data['overview']['headline']}",
        "",
        f"Status: `{data['status']}`.",
        "",
    ]
    if data["overview"].get("key_gap"):
        lines += [f"> Still missing: {data['overview']['key_gap']}", ""]
    lines += [
        "## The creative approach",
        "",
        data["overview"]["creative_strategy"],
        "",
    ]
    if data.get("script"):
        lines.extend(duration_lines(data))
        chosen = next(item for item in data["hook_options"] if item["hook_id"] == data["script"]["selected_hook_id"])
        lines.extend([
            "## The opening to use",
            "",
            f"**Say**: {chosen['spoken_line']}",
            f"**On screen**: {chosen['on_screen_text']}",
            f"**First frame**: {chosen['first_visual']}",
            "",
            "## The script, ready to shoot",
            "",
            "| Time | Say | Visual / on screen |",
            "|---|---|---|",
        ])
        for scene in data["script"]["scenes"]:
            visual = f"{scene['visual_direction']} / {scene['on_screen_text']}"
            lines.append(f"| {scene['timecode']} | {scene['spoken_text']} | {visual} |")
        lines.extend(["", f"**CTA**: {data['script']['cta']['spoken_text']}", ""])
    if data.get("packaging"):
        recommended = next(item for item in data["packaging"]["headline_options"] if item["headline_id"] == data["packaging"]["recommended_headline_id"])
        visual = data["packaging"]["cover_or_thumbnail"]
        lines.extend([
            "## Publishing package",
            "",
            f"- **Recommended headline**: {recommended['text']}",
            f"- **Cover / thumbnail**: {visual['primary_concept']}",
            "",
            "### Caption / Description",
            "",
        ])
        lines.extend(markdown_quote(data["packaging"]["caption_or_description"]))
        lines.append("")
    if data["interaction"]["required_questions"]:
        lines.extend(["## Confirm before you shoot", ""])
        for index, question in enumerate(data["interaction"]["required_questions"], 1):
            lines.append(f"{index}. {question['question']}")
        lines.append("")
    lines.extend(["## Next", "", data["overview"]["next_action"], ""])
    markdown = "\n".join(lines)
    validate_concise(markdown, data)
    return markdown


def full(data: dict) -> str:
    """Render all script, production and evidence details."""
    lines = [
        "# Script & Packaging — full production package",
        "",
        f"Status: `{data['status']}`; approval: `{data['approval_status']}`; revision: `{data['revision']}`.",
        "",
        "## Frozen input",
        "",
        f"```json\n{json.dumps(data['input_snapshot'], ensure_ascii=False, indent=2)}\n```",
        "",
        "## Hook options",
        "",
    ]
    lines.extend(duration_lines(data))
    for hook in data["hook_options"]:
        marker = " (recommended)" if hook["recommended"] else ""
        lines.extend([
            f"### {hook['hook_id']}{marker}", "",
            f"- Mechanism: {hook['mechanism']}", f"- Say: {hook['spoken_line']}", f"- On screen: {hook['on_screen_text']}",
            f"- First frame: {hook['first_visual']}", f"- Promised payoff: {hook['promised_payoff']}",
            f"- Proof required: {'; '.join(hook['proof_required']) or 'none'}", f"- Risk: {hook['risk']}", "",
        ])
    if data.get("script"):
        lines.extend(["## Full script", ""])
        for scene in data["script"]["scenes"]:
            lines.extend([
                f"### {scene['order']}. {scene['timecode']} — {scene['purpose']}", "",
                f"- Say: {scene['spoken_text']}", f"- Visual: {scene['visual_direction']}", f"- On screen: {scene['on_screen_text']}",
                f"- Evidence: {', '.join(scene['evidence_refs']) or 'none'}", f"- Asset: {scene['asset_status']}", f"- Claim: {', '.join(scene['claim_ids']) or 'none'}", "",
            ])
        lines.extend(["### CTA", "", data["script"]["cta"]["spoken_text"], ""])
    if data.get("packaging"):
        lines.extend(["## Packaging", "", "### Headline options", ""])
        for item in data["packaging"]["headline_options"]:
            lines.append(f"- `{item['headline_id']}` {item['text']} — {item['strategy']} ({item['evidence_status']})")
        visual = data["packaging"]["cover_or_thumbnail"]
        lines.extend([
            "", "### Caption / Description", "", data["packaging"]["caption_or_description"], "",
            f"Hashtags / tags: {', '.join(data['packaging']['hashtags_or_tags'])}",
            f"Keyword research: {data['packaging']['keyword_research_status']}", "",
            "### Cover / thumbnail brief", "", f"- Kind: {visual['kind']}", f"- Information split: {visual['information_split']}",
            f"- Primary concept: {visual['primary_concept']}", "- Variants: " + "; ".join(visual["variants"]), "",
        ])
    lines.extend(["## Production plan", ""])
    for label, key in (("Shot list", "shot_list"), ("Edit notes", "edit_notes"), ("Available", "available_assets"), ("Missing", "missing_assets")):
        lines.append(f"### {label}")
        lines.extend([f"- {item}" for item in data["production_plan"][key]] or ["- none"])
        lines.append("")
    lines.extend(["## Claim ledger", ""])
    for item in data["claim_ledger"]:
        lines.append(f"- `{item['claim_id']}` **{item['status']}** — {item['text']}; Action: {item['required_action'] or 'none'}")
    lines.extend(["", "## Quality checks", ""])
    for item in data["quality_checks"]:
        lines.append(f"- **{item['check']} / {item['status']}** — {item['detail']}")
    lines.extend(["", "## Provenance", "", f"```json\n{json.dumps(data['provenance'], ensure_ascii=False, indent=2)}\n```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_package", type=Path)
    parser.add_argument("--concise", type=Path, required=True)
    parser.add_argument("--full", type=Path, required=True)
    args = parser.parse_args()
    data = load(args.script_package)
    args.concise.write_text(concise(data), encoding="utf-8")
    args.full.write_text(full(data), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
