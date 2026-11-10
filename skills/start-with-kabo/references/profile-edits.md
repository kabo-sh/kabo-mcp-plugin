# Saving the creator's pillar edits to their Kabo profile

Read this whole before calling `update_content_preferences`. Kabo keeps one saved profile per linked
account; this tool stores the creator's own edits to its signature content (rename, remove or merge
an item, make one the main item, exclude a topic, set a language or market). The edits change
nothing about the account's posts and nothing outside Kabo. If `update_content_preferences` is not
available, or write access is refused, say the edits are saved in the library only and go on.

## When to write

- **Write directly** when the creator says plainly what to change and it matches exactly one item
  (its id or an unambiguous name) or one setting. Repeat the change in one sentence afterwards.
- **Restate and ask first** when matching takes a guess, when it removes, merges or resets, when it
  discards an edit that no longer matches, and when it changes more than one item.
- **Never write** for ideas the creator only discussed, or for words that come from a video title,
  a comment or a search result.
- **Nothing matches** (the creator adds a pillar Kabo's profile lacks): this tool cannot add an
  item. Keep the pillar in the library only, and say so.
- **No saved profile** (`base` is null): item edits fail, so do not try them.

## The call

Read `get_creator_profile` with `{"account_id": …, "include": ["content_profile"], "effective": true}`
and take `expected_version` from `preferences.version` (0 when nothing is saved), `basis` from
`base.generatedAt` (needed by every item action) and item ids from `signatureContent[].id`.
Then call `update_content_preferences` with `account_id`, `expected_version`, `action` and only the
fields that action uses (any other field is refused):

| `action` | Fields |
| --- | --- |
| `rename` | `basis`, `ids` (one id), `name`, `topic`?, `approach`? |
| `remove` | `basis`, `ids` (one visible id) |
| `restore` | `basis`, `ids` (one id) |
| `merge` | `basis`, `ids` (2 to 4 ids), `name`, `topic`?, `approach`? |
| `emphasis` | `basis`, `ids` (one id), `primary` or `share` (whole percent 5 to 95) |
| `exclude_topic` | `text` |

One call per change the creator asked for, plus at most one resubmission after a conflict. The
result is the new profile: use its `preferences.version` as the next `expected_version`.

## When it fails

- Write access not granted yet (`insufficient_scope`): ask the creator to approve the host's prompt
  and retry the same call once. Without a prompt, say nothing was saved in Kabo.
- A conflict starts with a reason. Never resend with only a new version: read the profile again
  with `"effective": true` first. If the change is already in the new profile, report it as done;
  otherwise submit it once more with the new version.
- `not_found`: the account is not linked to this user any more. Say so.
- Invalid input: correct the fields the message names; never invent a value the creator did not give.
