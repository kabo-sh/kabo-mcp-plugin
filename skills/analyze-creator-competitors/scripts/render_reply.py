#!/usr/bin/env python3
"""Write the Creator-facing reply for a validated CompetitorResearchReport V3, in the Report's language.

The reply used to be the last model turn of a run: the model re-read the rendered report and retyped
it as a relay card in the Creator's language — about 1,400 output tokens, measured 25–46 s on
2026-09-18, for text whose every sentence already sat in the validated Report (the synthesis prose is
written in the Creator's language) and whose numbers the Composer had already attached. This writes
that relay deterministically: overview, the compared accounts, up to three findings with their
strongest proof and the Creator's differentiation, then what nobody is doing, closed by one fixed
sentence of measurement basis (analyzed posts, accounts, window and the baseline size behind a shown
multiple). Known zero-sample accounts are named separately and never counted as compared. Other raw
data gaps and the next-step plan stay in the Report for follow-up questions.

The existing labels follow the Report's `scope.locale.language` primary subtag, with English for
unlisted languages. The zero-sample notice has one English template; the main agent translates the
complete report for delivery when needed. Everything else is the Report's own text and data.

usage: render_reply.py <competitor-research-report.json> <creator-reply.md>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_basis import ENGLISH as BASIS_EN, basis_sentence, shown_multiple_sample_sizes  # noqa: E402
from render_creator_report import (  # noqa: E402
    content_map,
    display_title,
    end_sentence,
    link_accounts,
    select_pattern_evidence,
    comparison_basis,
    zero_sample,
    zero_sample_refs,
    ZERO_SAMPLES,
)

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "roster": "Compared accounts", "direct": "direct", "adjacent": "adjacent", "media": "media",
        "adjacent_evidence": "Adjacent evidence:", "media_evidence": "Media evidence:",
        "differentiation": "How you can differ:", "gaps": "What nobody is doing yet",
        "views": "{n} views", "multiple": "{m}× the account's usual",
        "not_compared": "Requested accounts not compared (no verified public evidence; no substitute was used): {refs}.",
    },
    "zh": {
        "roster": "对比的账号", "direct": "直接竞品", "adjacent": "相邻参考", "media": "媒体参考",
        "adjacent_evidence": "相邻参考证据：", "media_evidence": "媒体参考证据：",
        "differentiation": "你可以怎么不同：", "gaps": "还没人做的",
        "views": "{n} 次播放", "multiple": "该账号常态的 {m} 倍",
        "not_compared": "以下指定账号没有可核实的公开数据，未纳入对比，也没有用其他账号替代：{refs}。",
    },
    "pt": {
        "roster": "Contas comparadas", "direct": "direto", "adjacent": "adjacente", "media": "mídia",
        "adjacent_evidence": "Evidência adjacente:", "media_evidence": "Evidência de mídia:",
        "differentiation": "Como você pode se diferenciar:", "gaps": "O que ninguém está fazendo ainda",
        "views": "{n} visualizações", "multiple": "{m}× o normal da conta",
        "not_compared": "Contas solicitadas não comparadas (sem evidência pública verificável; nenhuma substituta foi usada): {refs}.",
    },
    "es": {
        "roster": "Cuentas comparadas", "direct": "directo", "adjacent": "adyacente", "media": "medio",
        "adjacent_evidence": "Evidencia adyacente:", "media_evidence": "Evidencia de medios:",
        "differentiation": "Cómo puedes diferenciarte:", "gaps": "Lo que nadie está haciendo aún",
        "views": "{n} reproducciones", "multiple": "{m}× lo habitual de la cuenta",
        "not_compared": "Cuentas solicitadas no comparadas (sin evidencia pública verificable; no se usó ninguna sustituta): {refs}.",
    },
}
BASIS: dict[str, dict[str, str]] = {
    "en": BASIS_EN,
    "zh": {"count": "基于 {count} 条公开内容", "no_count": "基于公开内容", "accounts": "（{accounts} 个账号）",
           "window": "，发布于 {since} 至 {until}", "multiple": "；倍数是与同账号同形式内容的基线相比（{n}）", "end": "。"},
    "pt": {"count": "Com base em {count} publicações públicas", "no_count": "Com base em publicações públicas",
           "accounts": " de {accounts} contas", "window": " publicadas de {since} a {until}",
           "multiple": "; os múltiplos comparam cada post com a linha de base do mesmo formato da mesma conta ({n})"},
    "es": {"count": "Basado en {count} publicaciones públicas", "no_count": "Basado en publicaciones públicas",
           "accounts": " de {accounts} cuentas", "window": " publicadas del {since} al {until}",
           "multiple": "; los múltiplos comparan cada publicación con la línea base del mismo formato de la misma cuenta ({n})"},
}
# Creator-facing outlier proof needs at least five comparables and at least 1.5× (SKILL step 5).
MIN_COMPARABLES = 5
MIN_MULTIPLE = 1.5


def labels_for(report: dict[str, Any]) -> dict[str, str]:
    language = str(((report.get("scope") or {}).get("locale") or {}).get("language") or "en")
    return LABELS.get(language.split("-")[0].lower(), LABELS["en"])


def number(value: float) -> str:
    return f"{int(round(value)):,}"


def proof_line(ref: str, report: dict[str, Any], content: dict[str, dict[str, Any]], text: dict[str, str]) -> str | None:
    item = content.get(ref)
    if not item:
        return None
    handles = {str(c.get("account_ref")): c for c in report.get("competitors") or []}
    account = handles.get(str(item.get("account_ref")), {})
    handle = str(account.get("handle") or "").lstrip("@")
    who = (f"[@{handle}]({account['url']})" if handle and account.get("url") and account.get("platform") != "youtube"
           else f"[{handle}]({account['url']})" if handle and account.get("url") else "")
    parts = [part for part in (who, f"[{display_title(str(item.get('title') or ref))}]({item['url']})") if part]
    views = (item.get("metrics") or {}).get("views")
    if isinstance(views, (int, float)) and not isinstance(views, bool):
        parts.append(text["views"].format(n=number(views)))
    for outlier in report.get("outliers") or []:
        if str(outlier.get("content_id")) != ref or outlier.get("ratio") is None:
            continue
        comparables = int((outlier.get("baseline") or {}).get("sample_size") or 0)
        ratio = float(outlier["ratio"])
        if comparables >= MIN_COMPARABLES and ratio >= MIN_MULTIPLE:
            parts.append(text["multiple"].format(m=f"{ratio:.1f}"))
    return "- " + " · ".join(parts)


def render_reply(report: dict[str, Any]) -> str:
    text = labels_for(report)
    content = content_map(report)
    overview = report["overview"]
    lines = [f"## {link_accounts(overview['title'], report)}", "", link_accounts(overview["summary"], report), ""]
    roster = []
    for item in report.get("competitors") or []:
        if zero_sample(item):
            continue
        handle = str(item.get("handle") or "").lstrip("@")
        if not handle:
            continue
        label = handle if item.get("platform") == "youtube" else "@" + handle
        name = f"[{label}]({item['url']})" if item.get("url") else label
        relationship = text.get(str(item.get("relationship") or ""), "")
        roster.append(f"{name} ({relationship})" if relationship else name)
    if roster:
        lines += [f"**{text['roster']}** " + ", ".join(roster), ""]
    empty = zero_sample_refs(report)
    if empty:
        lines += [link_accounts(ZERO_SAMPLES.format(refs=", ".join(empty)), report), ""]
    relationships = {str(item.get("account_ref")): str(item.get("relationship") or "")
                     for item in report.get("competitors") or []}
    cited: list[str] = []
    for index, pattern in enumerate((report.get("patterns") or [])[:3], start=1):
        lines += [f"### {index}. {pattern['pattern']}", "", link_accounts(end_sentence(pattern["mechanism"]), report), ""]
        selected = select_pattern_evidence(pattern, report, content)
        cited += [ref for ref, _ in selected]
        # The same downgrade render_creator_report.py marks: a finding whose proof comes from no direct
        # competitor is adjacent (or media) evidence, and says so before the proof.
        kinds = {relationships.get(str(content[ref].get("account_ref"))) for ref, _ in selected if ref in content}
        if kinds and "direct" not in kinds:
            lines.append(f"*{text['adjacent_evidence' if 'adjacent' in kinds else 'media_evidence']}*")
        for ref, _ in selected:
            line = proof_line(ref, report, content, text)
            if line:
                lines.append(line)
        lines += ["", f"**{text['differentiation']}** {link_accounts(pattern['differentiation'], report)}", ""]
    gaps = [g for g in report.get("gaps") or [] if isinstance(g, dict) and g.get("summary")]
    if gaps:
        lines += [f"### {text['gaps']}", ""]
        lines += [f"- {link_accounts(end_sentence(g['summary']), report)}" for g in gaps[:2]]
    missing = [str(ref) for ref in (report.get("coverage") or {}).get("requested_not_compared") or []]
    if missing:
        lines += ["", text["not_compared"].format(refs=", ".join(missing))]
    language = str(((report.get("scope") or {}).get("locale") or {}).get("language") or "en")
    template = BASIS.get(language.split("-")[0].lower(), BASIS["en"])
    basis = basis_sentence(comparison_basis(report), shown_multiple_sample_sizes(report, cited), template)
    if basis:
        lines += ["", f"*{basis}*"]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        args.output.write_text(render_reply(report), encoding="utf-8")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
