`synthetic-get-analysis-run.json` is a synthetic, schema-valid `get_analysis_run` result built from the
MCP output schema in `contracts/directory-mcp/tools-list.json`, not a recording. Every field the analysis must
discard carries a `SENTINEL-` marker so a test can prove none of it reaches the evidence or the brief. Replace it
with a real recorded result once one exists.
