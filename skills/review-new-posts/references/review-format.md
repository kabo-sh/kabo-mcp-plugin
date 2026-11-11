# Review and recap format

Write in the creator's language, in plain sentences a busy creator reads in under a minute. Lead
with the verdict, then the numbers that support it, then what to do. No tables, no jargon, no
abbreviations they would not use themselves.

## The daily report

One message per run, always in this order:

1. **Account recap** (every run, even when no post is due).
2. **Post reviews** (one block per review made in this run; none when nothing was due).
3. **Skipped or limited**, one line each, only when something was skipped or `limits` listed any.

## Account recap

Use the `recap` output. Four short parts, no tables:

```markdown
**Your account today · <platform> @<handle>**

**Followers:** <now, and the change since the earlier reading with how long ago it was; or "no
earlier reading yet">.

**Last 7 days:** <how many posts, the median views of those that are settled against typical
("1.4 times your usual"), which one led and which one trailed with a link each; say how many are
still gathering views>.

**Your pillars:** <one line per pillar: posts in the last 7 days, median views against typical,
and whether its latest three do better or worse than the ones before, when the numbers exist.
Name a pillar you have not posted in for two weeks or more.>

**One thing to do next:** <one concrete recommendation tied to a number above: the topic or pillar,
the first line, what is on screen>.
```

- The recommendation is exactly one, specific enough to film tomorrow, and stays inside the
  creator's pillars (when there are any) unless the numbers show a pillar is not working.
- Words for a ratio: "well ahead of" (2 times or more), "ahead of" (1.2 to 2), "in line with"
  (0.8 to 1.2), "behind" (0.5 to 0.8), "well behind" (under 0.5). Use the number too.
- Leave out **Your pillars** when the recap has no pillars (Kabo has not found any for this account
  yet); never make pillars up.
- Follower change only when `followers.available` is true. Otherwise say there is no earlier
  reading yet. Never estimate it.
- Posts under 72 hours old are still gathering views: do not rank them against typical.
- Public metrics only. Never state or estimate watch time, retention, reach, saves or shares unless
  the output has them, and never blame the algorithm, a shadowban or posting time without evidence.

## Post review

```markdown
**<Post title, first 8 words> · <24-hour | 1-hour | 7-day> review**

<Verdict: one sentence, with the main number and what it is compared with.>

<Numbers: two or three sentences. Views, likes and comments at this age; engagement rate against
their usual; views per hour since the last check when there was one.>

<What people say (24 hours and 7 days only, when comments were read): the two or three themes, with
one short quote each, or "No comments yet.">

**Next video**
1. <A concrete suggestion tied to this result.>
2. <A second one, different in kind.>

<Limits, one line, only when review-facts listed any.>
```

## Choosing the comparison

1. `same_age_baseline.multiple` exists (3 or more earlier posts measured at this checkpoint, and
   this post was measured there too): use it. "1,840 views at 24 hours, 1.8 times what your posts
   usually have at 24 hours."
2. Otherwise use `typical_settled.share_reached` and say what it is: "It has reached 36% of the
   views your posts usually end up with." Never call this a same-age comparison.
3. For the 7-day review, also compare with `pillar_settled` when it has 3 or more posts.
4. A review marked late (the post is already past 48 hours) says so in one clause and compares with
   typical, not with the 24-hour mark.

## What each checkpoint is for

- **24 hours** (the default): whether it took off. Comments are worth reading now: questions people
  ask are the best source of the next video. Suggestions: a follow-up that answers the top
  question, a second version of the same idea with a stronger first line.
- **1 hour** (optional, only on request): the opening and the first audience. It is early: do not
  call a post a failure.
- **7 days** (optional, only on request): the final result. Say whether to make more of this pillar
  or this angle, and the single thing to change next time.

## Next-video suggestions

- Tie each one to evidence in this review: a number, a comment theme or the pillar comparison.
- Make it specific enough to film tomorrow: the topic, the first line, what is on screen.
- Stay inside the creator's pillars unless the comments clearly ask for something else; then say
  that it is outside their pillars.
- When the post did well, the first suggestion is usually a follow-up or a part two. When it did
  poorly, change one thing (the opening line, the angle or the length), not everything.

## Never

- Never state or estimate watch time, retention, reach, saves or shares unless `review-facts`
  returned them.
- Never promise a result.
- Never reply to a comment or contact anyone.
