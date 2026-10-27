# Supplementary facts for a selected brief

Reuse the conversation through the target turn, including the named account's
intended audience and the stated CTA. Do not invent demographics, approval or a
selected topic. An explicit request to script a named product/direction may use
the existing direct-selection builder; preserve the exact topic span. Required
constraints still missing need the existing minimal clarification.

For missing product facts, first check source identity and the actual reader's
scope. A product page needs a product/general-web reader the host permits, or
page text the creator supplies; a help/news-only reader's domain rejection is a
tool mismatch, not proof the product information is unavailable. Never widen an
allowlist. Check readiness and declared source/host coverage
(`creative_evidence.source_route`); stop and record unavailable paths. Social
evidence still comes from Kabo platform data (another Skill's output), not an
undisclosed web substitute. Reuse already captured pages when suitable.

Record a `creative-evidence-input.v1` with `evidence_id`, `expected_products`
(each has exact `url`, `brand`, `product_id`) and `pages`. Each captured page has
those same identity fields, `source_type: brand_product_page`, `retrieved_at`,
original `text` and `facts`. Each fact has unique `id`, `kind` (`identity`,
`components`, `brand_claim`), a verbatim `excerpt`, and reviewed `report_text` in
the output language. Match the actual brand and product, not just a similar name;
the helper verifies declared identity and exact excerpts, not semantic truth.
Review every projected sentence against its excerpt. Do not classify efficacy,
universal suitability, sales or personal experience as identity/components.
Brand marketing is an attributed statement, not independent efficacy evidence.
Contradictory stock, price or shipping text is not a current promise.

Run `cd '<run>' && python3 '<skill directory>/scripts/creative_evidence.py' --input
captured-products.json --output creative-evidence.json`. Reference the resulting artifact via optional request
`supplemental_evidence` (`path`, `artifact_id`, `schema_version`, exact file
`sha256`). The input snapshot freezes this reference separately: it does not
change SelectedIdea selection, its evidence refs, or its evidence basis. Claims
may reference supplementary fact IDs; their text must match the reviewed fact
projection. Only identity/components can be verified from a brand page. The
validator rebuilds the evidence against hashed captured input; the run manifest
records both files. Preserve the usual claim linkage for every factual surface.
Unknown efficacy need not block a pure product display with supported wording.

For account style, choose a small relevant sample (usually 3–5 only when needed),
not unrelated high-view clips. Inspect actual frames; use validated ContentEvidence
and VideoAnalysis. `audiovisual_scope` checks source identity, inspected frame IDs
and speech timing against duration. Pass `transcript_reviewed=True` only after
checking actual speech/recognition quality. Noisy recognition or mismatched timing
cannot supply quoted dialogue or voice imitation. A few frames support those
frames, not continuous editing rhythm or the entire account's habitual style.
Finite sample-based adaptations can still be useful; do not require private
algorithm knowledge, guaranteed virality or sales to deliver ideas. State which
requested dimensions remain unassessed and never weaken the original task.

Monthly music needs dated monthly popularity evidence. A usage example or a
lifetime count is not that evidence. If registered capabilities cannot provide it,
retain the bounded partial result; do not fill a requested quantity with unrelated
tracks or repeated searches of the same undated catalog.

Fact-bearing scenes link the corresponding claim ID. For a scene or hook that
cites supplementary facts, spoken text must equal the reviewed report projection
(multiple facts joined with a space in fact-ID order); the on-screen text is the
same projection or empty. Keep creative narration in separate scenes. This
prevents an unrelated statement borrowing a valid fact ID. Semantic review of
translations and uncited creative prose remains necessary; hashes do not prove
that a natural-language statement is true.

When supplementary evidence is supplied, add `publishable_claim_links` to the
package: one `{path, claim_ids, evidence_refs}` entry for every nonempty text
surface enumerated by `publishable_claim_surfaces`. Paths include
`packaging.headline_options[0].text`, `packaging.caption_or_description`,
`packaging.cover_or_thumbnail.variants[0]`, and `script.cta.spoken_text`, as well
as overview, hook and scene text. Factual fields link the reviewed claim and its
source; creative prose explicitly uses empty lists. Never classify a factual
assertion as creative to avoid a check. The validator checks known paths, claim
status and exact source-projected wording; uncited natural language still needs
semantic review and cannot be certified by a deterministic validator. Existing
scene/hook references are retained even when a field link is empty.

Evidence artifact and captured-input paths must be relative and resolve inside the run directory before either file is read, including symlinks. Native request/package validation defaults to the request directory; when the request lives in a nested folder, pass `--run-root <run-directory>` to the validator. Calendar and run-manifest validation pass their existing run root explicitly. An input outside that root is not a valid supplementary reference.
