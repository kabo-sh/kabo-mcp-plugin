# Content pillars: propose, confirm, save to Kabo

A content pillar is what the creator is known for on this account: a recurring subject plus the
promise it makes to the viewer, narrow enough that someone else could search for comparable videos.
The niche is one level above it. Kabo uses the saved pillars for the daily picks, and reviews compare
new posts within a pillar, so a vague pillar makes both worse.

## Who decides

You propose; the creator decides; Kabo keeps what the creator confirmed.

- Your proposal comes from reading this run's posts and transcripts. Its numbers (`propose-pillars`)
  are a local reading of those posts, **not Kabo's statistics**. Never say "Kabo found" about it.
- Kabo's own signature content (`candidates` from `profile-pillars`, when the account has a Kabo
  profile) is shown next to your proposal as a reference, labelled "What your numbers show…". The creator
  can take any of it, word it their way, or leave it.
- Pillars the creator saved earlier (`declared_pillars`) are their current pillars; change them only
  when they ask.
- Once confirmed, the whole set is saved to Kabo in one `update_content_preferences` call with
  `action: "declare_pillars"` (SKILL step 5). It replaces what Kabo held; an empty list would clear it.

## The shape Kabo stores

| Field | Rule |
|---|---|
| `name` | 1 to 60 characters; no two pillars share a name, ignoring case |
| `definition` | one sentence of 1 to 200 characters: the subject and the promise |
| `search_phrases` | 1 to 3 phrases a viewer would type, each 1 to 60 characters |

At most 4 pillars. `propose-pillars` and `save-pillars` check these limits first: shorten what they
report, never send text that breaks them.

## What to read

- The `posts` table: title or caption, views, multiple of typical views, age.
- The transcripts. The first sentence usually states the promise of the video.
- Ignore hashtags unless the caption has nothing else; they describe reach hopes, not content.

## How to group

Ask of every post: **what is it about, and what does the viewer walk away with?**

| Signal | Use it | Do not use it |
|---|---|---|
| Subject (a product category, a skill, a story type) | yes | |
| Promise to the viewer (learn a technique, see a transformation, laugh at a situation) | yes | |
| Format (talking head, voice-over, carousel, skit) | | it is how, not what |
| Length, posting time, hashtags | | |
| The broad niche ("fitness", "marketing", "food") | only as context | it is one level too high |

Good pillars are one level below the niche:

| Niche | Pillars |
|---|---|
| Fitness | "15-minute home workouts with no equipment"; "what I eat in a day while cutting" |
| Content creation | "why one specific viral video worked"; "how to be more charismatic on camera" |
| Personal finance | "first-job money mistakes"; "explaining one investing term with a real example" |
| Food | "one-pan dinners under 20 minutes"; "rating viral recipes honestly" |

## Reading the numbers

`propose-pillars` prints, per pillar, how many posts it holds, their median views, that median as a
multiple of the account's typical views (the median of posts at least 72 hours old) and its share of
views. As a rough guide only: a group whose median is well under typical (below about 0.8 times) or
that holds a small share of views (under about 20%) may be weaker. Mention it once when it helps the
creator choose; never reject a pillar the creator wants.

## Search phrases

- Concrete enough to find videos like the creator's, broad enough to find more than a handful:
  "viral hook breakdown" works; "hooks" is too broad; a single video's title is too narrow.
- No hashtags, no handles, no brand names unless the pillar is about that brand.

## Edge cases

- **One-topic accounts.** One pillar is fine.
- **Promotional posts.** Posts that mainly sell the creator's own product are rarely a pillar.
- **Too few posts.** With fewer than about 5 posts, say the proposal is thin and let the creator's
  own words decide the pillars.
- **The creator disagrees.** Their choice wins. Mention the numbers once so the choice is informed.
