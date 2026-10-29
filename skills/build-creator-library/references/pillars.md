# Finding content pillars

A pillar is what the creator is known for on this account, stated so precisely that someone else
could search for comparable videos. Daily picks search with each pillar's queries, and reviews
compare new posts within a pillar, so a vague pillar makes both useless.

## What to read

- The `posts` table: title or caption, multiple of typical views, age.
- The transcripts from step 5. The first sentence usually states the promise of the video.
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

Each pillar's `definition` says the subject and the promise in one sentence.

## Search queries

- One to three phrases a viewer would type, in the audience's language.
- Concrete enough to find videos like the creator's, broad enough to find more than a handful:
  "viral hook breakdown" works; "hooks" is too broad; "why the wine pie zipper video got 7,673
  comments" is too narrow.
- No hashtags, no handles, no brand names unless the pillar is about that brand.

## Edge cases

- **One-topic accounts.** One cluster may hold almost every post. That is fine: one pillar.
- **Mixed accounts.** Personal vlogs next to tutorials: still group by subject and promise; the
  rule then picks what actually earns the views.
- **Promotional posts.** Posts that mainly sell the creator's own product form their own cluster
  ("product announcements"); they are rarely a pillar.
- **Too few posts.** When `pillars` reports `insufficient_history`, show the clusters and let the
  creator choose. Their stated intent is then the pillar, and the library records it.
- **The creator disagrees with the rule.** Their choice wins (`--choose`). Mention the numbers once
  so the choice is informed, without arguing.
