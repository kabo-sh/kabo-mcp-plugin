"""One fixed sentence stating what a Creator-facing report is based on.

The validated Report keeps the full measurement record — window, collected and eligible counts,
comparable baselines and data gaps. The Creator-facing text shows only this one sentence; when the
Creator asks for more, the host answers from the structured Report. Unknown values are left out,
never filled with zero, and cited examples are never presented as the analyzed population.

Every package that renders a Creator-facing trend or competitor report carries this same file.
"""

from __future__ import annotations

from typing import Any, Iterable

# Creator-facing multiples need at least five comparables and at least 1.5x.
MIN_COMPARABLES = 5
MIN_MULTIPLE = 1.5

ENGLISH = {
    "count": "Based on {count} public posts",
    "no_count": "Based on public posts",
    "accounts": " from {accounts} accounts",
    "window": " published {since} to {until}",
    "multiple": "; multiples compare a post with the same account's same-format baseline ({n})",
}


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _day(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


def shown_multiple_sample_sizes(report: dict[str, Any], refs: Iterable[str]) -> list[int]:
    """Baseline sizes behind the multiples a renderer can show for these cited refs."""
    wanted = {str(ref) for ref in refs}
    sizes: set[int] = set()
    for item in report.get("top_content") or []:
        if str(item.get("content_id")) not in wanted or item.get("outlier_multiple") is None:
            continue
        size = _count((item.get("baseline") or {}).get("sample_size"))
        multiple = item["outlier_multiple"]
        if size and size >= MIN_COMPARABLES and _number(multiple) and multiple >= MIN_MULTIPLE:
            sizes.add(size)
    for item in report.get("outliers") or []:
        if str(item.get("content_id")) not in wanted or item.get("ratio") is None:
            continue
        size = _count((item.get("baseline") or {}).get("sample_size"))
        ratio = item["ratio"]
        if size and size >= MIN_COMPARABLES and _number(ratio) and ratio >= MIN_MULTIPLE:
            sizes.add(size)
    return sorted(sizes)


def basis_sentence(report: dict[str, Any], sample_sizes: Iterable[int] = (),
                   template: dict[str, str] | None = None) -> str:
    """The single basis sentence, or an empty string when nothing about the basis is known."""
    text = template or ENGLISH
    coverage = report.get("coverage") or {}
    window = (report.get("scope") or {}).get("window") or {}
    count = _count(coverage.get("eligible_count"))
    accounts = _count(coverage.get("competitor_count"))
    since, until = _day(window.get("since")), _day(window.get("until"))
    if count is None and not (since and until):
        return ""
    sentence = text["count"].format(count=f"{count:,}") if count is not None else text["no_count"]
    if accounts:
        sentence += text["accounts"].format(accounts=accounts)
    if since and until:
        sentence += text["window"].format(since=since, until=until)
    sizes = sorted(set(sample_sizes))
    if sizes:
        n = f"n={sizes[0]}" if len(sizes) == 1 else f"n={sizes[0]}–{sizes[-1]}"
        sentence += text["multiple"].format(n=n)
    return sentence + text.get("end", ".")
