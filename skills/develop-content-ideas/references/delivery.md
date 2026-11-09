# Deliver the validated list

## Complete list is the default

A request for N ideas receives all N validated candidates, including each opening line,
filming direction and pending production condition, in the user's report language.
Ambiguous intent defaults to the complete list. Do not interpret a large count as permission
to abbreviate. Do not read the report back into a new model-written answer.

After core returns `status="ok"` for a generated list, run:

```sh
python3 '<skill directory>/scripts/deliver_ideas.py' --run-dir '<run directory>'
```

Only this successful export creates `FINAL_IDEAS.md` and `idea-delivery.json`.
It checks core state, the exact input digests recorded by core, the request, the IdeaSet,
and the exact renderer projection again.
A nonzero exit or `status="not_deliverable"` prohibits delivery; no final file remains.
`needs_revision` uses the existing single revision in the same run, never a fresh budget.
If repair cannot finish, explain that the requested list could not be validated. A terminal
missing-source/selection-context report is a clarification, not a completed idea list.

Pass the returned absolute `report_path` to the host's existing `emit_block` capability:

```json
{"block":{"type":"markdown","path":"<returned report_path>"}}
```

Use `path`, not a retyped `text` payload. Wait for successful emission before claiming delivery.
At most one short guiding sentence may accompany the emitted report; no duplicate list follows.
If emission was omitted, call it before ending. If it fails, retry the same unchanged path once;
if it still fails or the capability is unavailable, explain that the complete list could not be
displayed inline. If the host already supports attaching or linking an existing local file,
you may expose the unchanged final file that way and clearly identify it as a file delivery;
never invent a download URL or claim inline display succeeded. Without a verified file-delivery
capability, stop with that limitation. Do not rewrite the full report. Scripts never call a host API.
An explicitly requested strict JSON response retains the JSON-only contract; do not append
Markdown to it or claim that JSON is the rendered report.

## Explicit curated delivery

Only an explicit request such as "pick three from these" or "briefly explain a few" allows
a model-written selection or summary. For a new list, first validate/export the full source list.
For a follow-up to an already delivered validated list, reuse that exact list from retained
artifacts or visible conversation; do not recreate a fictional IdeaSet to pass a schema. Choose
only entries present in the source list. Preserve their original displayed numbers and titles; do not
renumber selected #2, #5, #8 as #1, #2, #3. Summaries may shorten their descriptions but must not
invent entries, openings, facts or production conditions. State which original numbers you picked.
If the request instead asks for three **new** ideas, generate and deliver three complete entries.

## Follow-up identity

Keep `idea_set.json`, `request.json`, the final report and `idea-delivery.json` together.
The receipt binds the report and source digests and maps displayed number to `idea_id`.
For "select N" or "edit N", resolve N in that exact displayed list, check the same title and ID,
and reuse the original fields. A selection is not a request to regenerate a batch; hand the
selected candidate and actual user choice to packaging when a script is requested. An edit
keeps that candidate's identity and unchanged constraints; do not silently edit another rank.
When files are not retained across turns, recover the numbered list from visible conversation
instead of inventing IDs; use the existing conversation-source input adapter. If neither source
is available, ask for that list. "Another batch" starts a new run using the real previous list
or visible history, preserving its mechanism/constraints and excluding unwanted repeats.
