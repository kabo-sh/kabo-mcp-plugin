# Finding content pillars

A pillar is what the creator is known for on this account, stated so precisely that someone else
could search for comparable videos. Daily picks search with each pillar's queries, and reviews
compare new posts within a pillar, so a vague pillar makes both useless.

## Start from what Kabo already knows

When `profile-pillars` returns candidates, they come from the creator's saved Kabo profile (their
signature content, with the creator's own earlier edits applied). Present those as the proposal and
let the creator change them. Compute pillars from the posts yourself only when Kabo has none, or
when the account is not saved in Kabo.

## What to read (local proposal)

- The `posts` table: title or caption, multiple of typical views, age.
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

Each pillar's `definition` says the subject and the promise in one sentence.

## The niche line

One plain sentence of at most 200 characters naming who the account is for and what it gives them,
written from what the posts say, for example "Short breakdowns of why specific videos went viral,
for small creators". It is context for the creator, not a search term.

## The rule behind the recommendation

`propose-pillars` ranks the clusters you wrote. A cluster is recommended only when its median views
are at least 0.8 times the account's typical views (the median of posts at least 72 hours old) and
it has enough such posts. Eligible clusters are ranked by share of the account's views; a second
pillar needs at least 20% of the views. A cluster the creator posts often but that usually does
worse than typical is not recommended; say so, because it is often the most useful finding. When no
cluster reaches typical views, `below_typical` is true: say the account has no clearly strong topic
yet. The rule recommends; the creator decides.

## Search queries

- One to three phrases a viewer would type, in the audience's language.
- Concrete enough to find videos like the creator's, broad enough to find more than a handful:
  "viral hook breakdown" works; "hooks" is too broad; a single video's title is too narrow.
- No hashtags, no handles, no brand names unless the pillar is about that brand.

## Edge cases

- **One-topic accounts.** One cluster may hold almost every post. That is fine: one pillar.
- **Mixed accounts.** Personal vlogs next to tutorials: still group by subject and promise.
- **Promotional posts.** Posts that mainly sell the creator's own product form their own cluster;
  they are rarely a pillar.
- **Too few posts.** When `propose-pillars` reports `insufficient_history`, show the clusters
  without a recommendation and let the creator choose. Their stated intent is then the pillar.
- **The creator disagrees with the rule.** Their choice wins. Mention the numbers once so the
  choice is informed, without arguing.
