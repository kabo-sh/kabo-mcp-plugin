# Provided Snapshot input

Read this file whole before the first command of this path. Use it when the user provides one
`public-content-snapshot.v1` for this skill's platform and asks to analyze that evidence, instead of
the collection Workflow. It makes no data calls. Every command runs from the run directory reserved
for this request; `<skill directory>` is the folder holding `SKILL.md`, and scripts and references
are read from there. Write new artifacts only in the run directory.

Preserve the supplied Snapshot bytes. Build one `TrendResearchRequest` from the user's requested
niche and mode, preserving the Snapshot's exact platform, window, locale and formats. Print the
Request schema once with `cat '<skill directory>/references/trend-research-request.schema.json'`
before writing the Request, and do not open it again. If the requested scope conflicts with the
supplied evidence, ask for compatible evidence or explicit permission for a separate fresh
collection; never silently change either scope or claim that historical evidence is current.

Validate the Request, Snapshot and their scope consistency before analysis:

```bash
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/validate_provided_snapshot.py' --request trend-research-request.json --snapshot <provided-snapshot-path>
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/analyze_public_snapshot.py' <provided-snapshot-path> --mode trend --request trend-research-request.json --output public-content-analysis.json
```

On validation or analysis failure, stop this path with the actual error. Do not create a query
plan, call collection or enrichment, reassemble the supplied Snapshot, invent a Gate or pass
`--relevance-gate` or `--trend-enrichment`.

Only the Workflow's `rank` prints the opening-pattern catalog, so print it here before writing the
synthesis:

```bash
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/prepare_hook_context.py' --platform instagram --purpose trends --output hook-context.json
```

Never reuse a synthesis created for a different analysis. Print
`references/trend-research-synthesis.schema.json` once the same way, then write one fresh
`trend-research-synthesis.v3.3` (here you write its `schema_version`, `request_id` and `report_id`) from the
intersection of the current Analysis's `relevance.candidate_content_ids`, ranked content and supplied
Snapshot evidence. Lexical overlap is recall, not proof of semantic relevance; exclude unsupported
references. Then follow this skill's existing synthesis rules (`references/ranking-and-synthesis.md`)
and Compose, Validate, Render and Idea-handoff requirements, passing the same supplied Snapshot path
to Compose. This chained command is the path's final step; its deliverable is `creator-report.md`:

```bash
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/compose_report.py' --request trend-research-request.json --snapshot <provided-snapshot-path> --analysis public-content-analysis.json --synthesis trend-research-synthesis.json --output trend-research-report.json \
&& python3 '<skill directory>/scripts/validate_output.py' trend-research-report.json --request trend-research-request.json --analysis public-content-analysis.json \
&& python3 '<skill directory>/scripts/render_creator_report.py' trend-research-report.json creator-report.md --language <the user's chat language> \
&& cat creator-report.md
```

A failed validator is not a deliverable; insufficient evidence is partial, not permission to invent
findings or recollect without consent.

This single-Snapshot path supports only conclusions justified by its existing public evidence. It
does not establish rising, falling, acceleration or confirmed momentum; do not combine multiple
snapshots or invent private metrics.
