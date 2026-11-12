# Synthetic creator-profile fixtures

The three `*.json` files are hand-written synthetic data taken from creator-skills #918
(`creator-skill-tests/trend-competitor-v3/fixtures/creator-profile/`), with only `review: null` added:
the pinned `get_creator_profile` outputSchema requires the three top-level fields `account`, `review` and `diagnosis`.
The shape is the `structuredContent` of `/mcp-pub`'s `get_creator_profile` (called with `include: ["content_profile"]`).
`scripts/trends-profile.test.mjs` first validates them against the outputSchema pinned in
`contracts/directory-mcp/tools-list.json`, so if the contract changes after the artifacts are re-pinned, this fails
first; update the fixtures to the new definition.

- Accounts, content ids and titles are all fictional and do not correspond to any real account.
- The TikTok fixture deliberately lists `signatureContent` in the reverse of weight order, to pin the
  "descending by weight, ties by id" ordering.
- The seed terms of the YouTube fixture's signature content are in Chinese, to pin substring matching for text
  written without spaces.

## Effective-profile fixtures (`*-effective*.json`)

Same shape as above, plus one more field, `effectiveContentProfile` (the output of `get_creator_profile` called with
`effective: true`); these are also validated against the pinned outputSchema first.

- `tiktok-effective.json`, `tiktok-effective-main.json`, `tiktok-effective-no-base.json`: taken from three vectors of
  kabo's `docs/contracts/effective-content-profile-v1.golden.json` (kabo-sh/kabo#1875, branch 43cb78325):
  `excluded_topics_language_and_market`, `primary_is_lifted_to_the_front` and
  `no_base_profile_keeps_settings_and_reports_edits`. The backend profile from the vector input goes into
  `contentProfile` (null when there is no backend profile) and the expected merged result goes into
  `effectiveContentProfile` unchanged; `account` reuses the one from `tiktok.json`. The merge rules exist only once,
  in kabo's domain package, and are not recomputed here.
- `instagram-effective.json`, `youtube-effective.json`: hand-written mirrors of `instagram.json` and `youtube.json`.
  The signature content is copied over unchanged, with the creator's own excluded topics and markets (BR, GB) added,
  to test that Instagram does not use the market and to test the default region of the YouTube collect call.
- When the golden file changes or the artifacts are re-pinned, regenerate from the new vectors; do not edit the merged
  result by hand.
