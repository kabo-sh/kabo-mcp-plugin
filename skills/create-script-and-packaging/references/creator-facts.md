# Creator facts and real-world claims

Read before writing any script, hook, caption or rewrite. It applies to every route: native
package, creative draft, partial edit and rewrite of the creator's own text.

## Lock the creator's facts before writing

The creator's own words are the source. Before drafting, list every fact in them that the copy
will use:

- dates and relative days: "tomorrow" stays tomorrow, "today" stays today, a weekday stays that
  weekday; never shift an announced event to the day of writing;
- numbers, prices, counts, levels, durations and rankings;
- names of people, places, products, works and characters;
- directions and outcomes: up or down, won or lost, rising or falling, approved or rejected;
- story and plot events, who did what, and the order they happened in;
- settings, roles and conditions the creator stated (location, cast, product material, ending line).

Copy each fact exactly into the copy. When you rewrite or tighten the creator's text, keep these
words and change only the wording around them. When the copy is in another language than the
creator's words, carry the same meaning and every number.

## Do not add facts nobody supplied

Do not state new facts about real people, teams, companies, products, markets, history or science
as if established: business segments, product lines, financial results, transfers, injuries,
scientific findings, archaeological finds. Use only what the creator or cited evidence supplied.
Otherwise turn it into the creator's opinion ("I think…"), an open question, or a visible
`[verify: …]` placeholder the creator fills in, or leave it out. Analysis of a stock, a player or
an event may use reasoning and questions; it may not invent the figures or events it reasons about.

## Check the finished draft

Write the facts file before the draft and the draft to a file, then run:

```sh
python3 '<skill directory>/scripts/check_user_facts.py' --facts '<workspace>/facts.json' --draft '<workspace>/draft.md'
```

`facts.json`:

```json
{
  "source_text": "<the creator's messages that supply facts, copied exactly>",
  "facts": [
    {"source": "<exact span of source_text>", "keep": ["<exact words of that span the draft must carry>"]},
    {"source": "<span>", "keep": ["<words>"], "rendered": "<exact draft span, only when the draft is in another language>"},
    {"source": "<span>", "omitted": true, "reason": "<why this fact is not used>"}
  ],
  "claims": [
    {"text": "<exact draft span stating a real-world fact>", "basis": "creator", "support": "<exact span of source_text>"},
    {"text": "<span>", "basis": "evidence", "ref": "<evidence id or URL it comes from>"},
    {"text": "<span>", "basis": "opinion"},
    {"text": "<span>", "basis": "question"}
  ]
}
```

`status="needs_correction"` lists each changed or dropped fact and each claim without a basis.
Correct the draft, not the facts file, and rerun once before delivery. The check is mechanical: it
proves the creator's words survived and each claim names a basis; it does not prove a claim true.
