// The account review renders its fixed words in the synthesis language, and tells the host when the printed
// report may be delivered as is instead of being retyped by the model.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scripts = fileURLToPath(new URL("../skills/review-creator-account/scripts", import.meta.url));

function python(code) {
  const result = spawnSync("python3", ["-c", code, scripts], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr + result.stdout);
  return result.stdout;
}

test("every catalog language carries every fixed word with the same placeholders", () => {
  python(String.raw`
import re, string, sys
sys.path.insert(0, sys.argv[1])
from compose_review import TEXT, ZH_TEXT, LOCALE_TEXT, _LOCALE_CATALOG

def fields(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    return [sorted(f for _, f, _, _ in string.Formatter().parse(v) if f) for v in values]

assert set(ZH_TEXT) == set(TEXT), set(TEXT) ^ set(ZH_TEXT)
for code, entry in _LOCALE_CATALOG.items():
    assert set(entry) == set(TEXT), (code, set(TEXT) ^ set(entry))
    for key, value in entry.items():
        assert fields(value) == fields(TEXT[key]), (code, key)
        assert type(LOCALE_TEXT[code][key]) is type(TEXT[key]), (code, key)
for key in ("published_at", "too_recent", "maturity_unavailable", "public_works", "public_hurts"):
    assert ZH_TEXT[key] != TEXT[key], key
`);
});

test("a catalog language renders no English fixed words; report_delivery says when the host may deliver it", () => {
  python(String.raw`
import sys
sys.path.insert(0, sys.argv[1])
from compose_review import TEXT, LOCALE_TEXT, identity_line, language_text, language_rendered, render_markdown, report_delivery

report = {
    "headline": "H", "diagnosis": "D", "status": "complete",
    "scope": {"platform": "instagram", "source_mode": "public", "window": {"start": "2026-10-01", "end": "2026-11-01"}},
    "data_coverage": {"content_total": 3}, "baselines": [{"format": "reel", "metrics": {"views": {"available_n": 5}}}],
    "what_works": [{"pattern": "P", "explanation": "E", "examples": [{"title": "T", "url": "https://example.com/1", "format": "reel",
        "metrics": {"views": 1200, "likes": 30, "comments": 1}, "published_at": "2026-10-20", "baseline_maturity": "mature",
        "view_multiple_vs_format_median": 1.5}]}],
    "what_hurts": [{"pattern": "Q", "explanation": "F", "examples": []}],
    "recommendations": {"continue": [{"action": "A", "success_metric": "M"}], "test": [{"action": "B"}], "stop": [{"action": "C"}]},
    "data_gaps": [],
}
english = [TEXT[k] for k in ("works", "hurts", "public_works", "public_hurts", "next", "next_primary", "next_tests", "next_stop", "criterion")]
for language in ("de", "pt-BR", "es-419", "it", "ko", "ja", "fr", "id", "vi", "ar", "hi"):
    assert language_rendered(language), language
    text = render_markdown(report, language)
    for word in english + ["views", "published "]:
        assert word not in text, (language, word, text)
    assert "The public bio" not in identity_line({"biography": "bio", "followers": 1200}, language_text(language))
    assert report_delivery(report, language) == "as_is", language
for language in ("en", "en-GB", "zh-CN", "zh"):
    assert report_delivery(report, language) == "as_is", language
for language in ("tr", "ru", "zh-Hant", "nl"):
    assert not language_rendered(language) or language.startswith("zh-Hant") is False
    assert report_delivery(report, language) == "translate", language
assert language_text("tr") is TEXT
blocked = {**report, "status": "blocked"}
assert report_delivery(blocked, "de") == "translate"
assert report_delivery(blocked, "zh-CN") == "as_is"
assert report_delivery({**report, "growth_estimate": {}}, "pt") == "translate"
`);
});
