# Optional metadata-only media audit

This maintainer diagnostic is separate from creator analysis. Run it only when explicitly
authorized to export a derived audit artifact. It makes no tool calls, decodes no images, changes
no source files and produces no conclusions. It never supplies viewing evidence or a case pass.

Use this run's root, the original media job plan and an explicit sources JSON list. Each list item
contains only `terminal` and optional `request_projection`, naming relative JSON paths under that
root. A terminal is the original job wrapper or terminal envelope; a request projection must be the
accepted connector evidence projection for that same job, never a model-authored replacement.
Missing projections, mismatched original params, data, hash or job identity, duplicate jobs or
ambiguous timestamps stay unknown. Establish source lineage independently from the real tool
result.

```json
[
  {"terminal":"snapshot/<actual terminal>.json","request_projection":"snapshot/<actual accepted projection>.json"}
]
```

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/sandbox_media_audit.py' --root <this run directory> --plan media_job_plan.json --sources <relative explicit sources.json> --output <this run directory>/media-audit.json
```

The output name is fixed (`media-audit.json`) and must sit under the source root. Existing outputs
are never overwritten; preserve closed run artifacts. Never manufacture an artifact reference or
copy an alleged request into a projection. An available ten-projection frame subset does not prove
all thirty request bindings; the rest remain gaps. Pass `--manifest <relative run-manifest.json>`
only when the run actually has one; without it the manifest stays `absent`, with no fabricated
closure.

The derived JSON contains only bounded status, operation and identity metadata, file and data
hashes, counts, frame seconds, bytes and hashes, and hashed object references. It excludes raw
captions, image bytes, URLs, object-reference strings, error text and provider contents. Do not
export original media envelopes as an ordinary user file. Stdout contains counts only. This
diagnostic leaves `source_origin_attested`, `image_delivery_proven` and `complete_case_pass` false.
An export alone does not establish a complete analysis: independently join the actual job and its
unique timestamp to delivered frame bytes and verify the report's claims.

Budgets: at most 64 JSON source files, 2 MiB per file and 8 MiB total. Exceeding a limit fails
explicitly; it never truncates accepted source evidence.
