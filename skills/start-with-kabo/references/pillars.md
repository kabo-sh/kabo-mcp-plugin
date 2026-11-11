# Presenting the niche and content pillars

A content pillar is what the creator is known for on this account: a recurring subject plus the
promise it makes to the viewer. The niche is one level above it. Reviews compare new posts within
a pillar, so the creator should recognise each pillar as their own.

## Where they come from

Only from the creator's Kabo profile. `prepare_creator_profile` has Kabo build it from the account's
public posts; `get_creator_profile` with `"effective": true` returns it with the creator's own
earlier edits applied, and `profile-pillars` turns it into the proposal: `niche` and up to four
`candidates`, each from one signature content item. Kabo decides which groups of posts qualify; this
Skill never groups posts, never adds a pillar of its own and never ranks the items differently.

## How to show them

- The niche in one plain line, as `niche` gives it. When it is empty, leave the line out.
- Each pillar: its `name`, one sentence of evidence and one example post as a link.
  - Evidence comes from `evidence`: `content_count` ("9 of your videos"), `median_multiple` ("1.8
    times your usual views") and `share_of_posts` ("about 30% of your posts"). `share_of_posts` is a
    share of posts, never of views. Leave out any number that is missing.
  - The example is the first of `evidence.examples` with a `url`.
- Follow every line of `advice`.
- `hidden_by_creator` lists items the creator removed earlier; do not show them as pillars. Mention
  that one can be brought back only when the creator asks about it.

## What the creator can change

Through `update_content_preferences` (see `references/profile-edits.md`): rename a pillar, drop it,
merge two to four into one, or make one the main pillar. Adding a pillar Kabo has not found is not
possible yet: say so plainly, and that Kabo may find it once there are more posts on that subject.
Nothing about pillars is saved anywhere else.

## When there are none

`status: no_signature_content`, a `prepare_creator_profile` answer of `insufficient_posts`, or a
profile that could not be built: say in one line that there are not enough videos yet for content
pillars (or that the profile could not be built), and go on with the rest of the session. Never
propose pillars from the posts, the niche or the creator's description instead.
