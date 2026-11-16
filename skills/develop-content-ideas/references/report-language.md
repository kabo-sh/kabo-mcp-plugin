# Report language and display translations

Use the latest explicit language instruction, otherwise the current request's language. Keep
`report_language` (report and interaction) separate from `language_targets` (creative content).
Use a BCP 47 tag on both request and set, preserving an explicitly requested region or script.
Recognized language names such as English and español normalize to their code. Do not translate
source quotations, evidence identifiers or retained user text just to match the report language.
Explain and generate new creative copy in the requested language; quotations can retain theirs.

## Fixed presentation is program-owned

Built-in catalogs cover zh/en/fr/ar/es and their regional variants; Traditional Chinese tags
(`zh-TW`, `zh-HK`, `zh-MO`, `zh-Hant`) get the Traditional catalog, so a creator writing Traditional
Chinese is tagged `zh-TW` (or their region), never plain `zh`. The renderer deterministically
supplies all interface labels and displayed status/intent/source-mode/effort values. **Do not author
translations of fixed UI labels or enum values for these languages.** Existing valid mappings in
older artifacts remain accepted, but cannot override fixed presentation. Canonical data is unchanged.

`evidence_gap_translations` still translates actual `evidence_summary.data_gaps` and displayed
`primary_evidence_ref` text, preserving every substantive limitation and original source string.
Supply one `{source_text, report_text}` per such source; when already in the requested language,
repeat it. Use `[]` when none exist. A gap called "low" is still a gap: translate its real meaning,
not the production-effort label. Do not add imaginary gaps to satisfy a diagnostic.

For another valid language without a built-in catalog (Bosnian, Turkish, Portuguese, German …),
keep that language's own tag as `report_language` (`bs`, `tr`, `pt-BR`); never set `en` or another
catalog language because the labels are missing. Print the entries to fill with
`python3 '<skill directory>/scripts/report_language.py' <report-language> --template` (or list them with
`--labels`), translate every `report_text`, and add them with the rendered values to
`evidence_gap_translations` in one pass, preserving Markdown markers and boundary spacing. The
validator rejects a report in such a language until every label is translated. If reliable
translation is unavailable, state the limitation; never silently switch language or bypass export.

## Repair and review

Read all returned errors together. `missing_required_source_texts` names only still-missing
mappings; `allowed_source_texts` lists literal source strings, not instructions. Keep valid entries,
remove duplicates/invalid entries, and repair empty translations. Do not change canonical enums,
evidence lineage, report language or source gaps merely to satisfy validation. Fixed-value omissions
are not errors in catalog-backed languages. Schema and independently detectable translation errors
must be repaired in the same permitted revision.

Structure checks cannot establish translation accuracy or that prose is actually in the requested
language. Before core, read titles, openings, filming directions and explanations for language
consistency. Preserve source text separately. Missing language is accepted only for identifiable
legacy Chinese inputs; it is not a way to suppress a translation error.
