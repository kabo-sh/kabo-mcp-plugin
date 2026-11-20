# Audience response

Deeper method for how viewers reacted to this post. Use it when the creator asks why it performed
as it did, how people responded, whether it was controversial, or what to make next from the
comments.

## Where audience evidence comes from

- **The comment summary** (`audience_response` in section 3): a paraphrase of a sample of the post's
  top comments, with a sentiment split, themes with their share of the sample, viewers' questions,
  their requests and a controversy flag. It carries no comment text and no commenter.
- **The public counts** (`public_metrics`): views, likes and the comment count. A count says how
  many, never what was said.
- **The video itself**: frames, transcript cues and notes. A theme is explained only by a moment
  that shows or says what the theme is about.

When section 3 says the comments were not read (an uploaded file, a platform the summary does not
cover, too few comments, or no summary available here), work from the comment count alone and say
in one plain sentence that the comments themselves were not read. Never guess what viewers said.

## Reading the summary

1. **Size first.** Say how many comments the summary rests on (`sample_size`) before any share.
   Every share is a share of that sample, which leans toward the earliest and most-liked comments;
   it is not the whole audience and not the people who watched without commenting.
2. **Sentiment is a rough split.** Report it as the summary gives it; a few points either way mean
   nothing. Mostly positive comments on a post that underperformed say that those who stayed liked
   it, not why others scrolled past.
3. **Themes, against the video's own moments.** For each theme worth reporting, find the moment it
   is about: the frame, cue or note where the thing viewers react to is shown or said. Cite both the
   theme and the moment. A theme with no matching moment (about the creator, another post, a
   product never shown) is reported as such, not pinned to a guessed time.
4. **Questions are gaps or hooks.** A question the video already answers points at a moment that
   was missed or unclear: name it. A question it never answers is material for the next post.
5. **Requests are demand.** What viewers ask the creator to make, show or explain next. Separate
   requests about this video (a missing step, a link) from requests for new content.
6. **Controversy.** When flagged, say what the disagreement is about from its note, and whether it
   is about a claim in the video (cite the moment), the creator, or something off topic. Do not call
   it good or bad for reach: comments alone cannot show that.

## Why it performed as it did

Comments explain reaction, not distribution. Pair them with the public counts and the video:
"the comments are mostly about the pan at 0:12, and nearly every question asks which pan it is"
is a reading; "it went viral because people loved it" is not. A comment count far above or below
what the views would suggest is worth one sentence; never compute a rate the evidence does not
carry, and never claim the comments caused the reach.

## What to make next

Turn the strongest question, request or theme into one or two concrete next posts, each citing the
item it comes from (`audience_response.questions[i]`, `audience_response.requests[i]`,
`audience_response.themes[i]`) and the moment in this video it builds on. Prefer what many in the
sample raised over a single striking item, and say when an idea rests on a small sample.

## Standards

| Strong | Weak |
|---|---|
| Sample size stated before any share | Shares presented as the whole audience |
| Each theme tied to the moment it is about | Themes listed with no link to the video |
| A next post built on a cited question or request | A generic "give the audience what it wants" |
| Controversy described by what it is about | Controversy treated as proof of success or failure |
| "The comments were not read" said once, plainly, when they were not | Reactions guessed from the counts |

## Do not claim

- **A comment's wording**, quoted or invented, or anything a named commenter said. The summary is a
  paraphrase; repeat its points in your own words.
- **That a share describes all viewers**, or that silent viewers felt the same.
- **That the comments caused the reach**, or that controversy helped or hurt distribution.
- **What viewers said** when the comments were not read.
