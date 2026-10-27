# Existing conversation script edits

Use this path for requested cover-text/opening alternatives to an identifiable
existing script. It does not require or fabricate SelectedIdea, source package
validation, production confirmation, or a marketing CTA. Keep the ordinary
ScriptPackage modes unchanged for full script/package work.

Read only the conversation through the current user turn. Reuse the user's
supplied script or an assistant script the user explicitly refers to for editing.
Verify that the referent (episode, title, quoted span) identifies that script;
`source_reference` substring validation alone cannot prove this semantic link.
If ambiguous, ask only which script. A request to revise a draft authorizes editing,
not approval of its facts or production readiness. Preserve names, plot, body,
closing, claims and their existing caveats. Do not redo unrelated research.

Freeze messages as `{ "messages": [{"id": "...", "role": "user|assistant",
"text": "exact original message"}] }`. Write a
`partial-script-edit-request.v1` with `request_id`, `source_message_id`,
`request_message_id`, `source_version` (SHA256 of exact UTF-8 source text),
`source_reference` (exact current request span naming that script), `language`,
`changes` (requested counts keyed by `opening` and/or `cover_text`) and
`cover_deliverable` (`text` when covers are requested, otherwise `none`).
Derive the hash with a local script; never type or invent it.

Before freezing, interpret the complete current user message,
including negation, quotations, historical requests, conjunctions and exact
counts, in the user's language. Supply `authorization_boundary` with:

- `message_sha256`: hash of the exact current user message;
- `source_span`: `{start, end, text}` naming the same `source_reference`;
- `entries`: objects with `change` (`cover_text` or `opening`), integer `count`
  from 1 to 50, and `span: {start, end, text}` containing the actual request;
- `excluded`: explicitly excluded cover/opening surfaces;
- `unresolved`: ambiguity descriptions; any nonempty list blocks freezing.

Span offsets count Unicode code points, with an exclusive end. Derive offsets
and hashes from the original text, never rewrite the message. The adapter checks
all spans, the whole-message hash, supported fields/counts, conflicts and source
reference separation, then requires `changes` to match the structured entries.
It does not infer semantic authorization from language-specific keywords. A
quoted or historical instruction is not current authorization; source titles
never authorize edits. You must verify these distinctions and the
referent before supplying the boundary, not mark them confirmed merely to pass
validation. Missing/ambiguous authorization requires the minimum clarification,
not a guessed boundary. Editing authorization is never production approval.
The result stage binds this exact boundary and message to the existing freeze.

Resolve cover modality from the current request and preceding deliveries.
Short cover wording following textual covers can continue as text, named as such.
Explicit image requests require actual image generation/delivery capability and
image artifacts. This adapter rejects image mode; do not relabel a brief as an image.

Run `cd '<run>' && python3 '<skill directory>/scripts/partial_script_edit.py' --request request.json
--conversation conversation.json --input edit-input.json`. Generate an edit result with:

- `schema_version: partial-script-edit.v1`, source version from the frozen input;
- `preserved_script`: exact source text, `language`: same as frozen input;
- `status: proposal`, `approval_status: pending`;
- `alternatives`: exactly the requested fields/counts of distinct text alternatives;
- localized `title`, `labels` (one per requested field), `boundary_note` and
  `selection_prompt`. State that these are text options and the remaining script
  is preserved. Ask the user to choose, without claiming automatic approval.

Run the same command with `--result edit.json --report creator-report.md` to
validate and render against the existing `edit-input.json`; this stage never
rewrites that file. It checks the request and conversation against the original
frozen message IDs, exact source version, authorization text and scope, rejecting
drift before rendering. Later turns are not imported. The freeze command requires
a new input path, so a new revision cannot silently replace an existing freeze.
It also rejects changed body text, wrong version, count, scope or approval. Review
actual language, distinct mechanisms, character/plot continuity and claims in
addition to deterministic checks. Alternatives do not replace the original
opening until selected; single-opening requests use count 1, still as a proposal.
