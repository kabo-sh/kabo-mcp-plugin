# Missing evidence without changing the task

Read this when the original request depends on external facts that the supplied, validated
artifacts do not establish. This Skill collects no research itself (only a video's comments, as
`comment-evidence.md` says); trend, competitor, account and video evidence comes from the JSON
output of the Skill that produces it. Before giving a final missing-input answer, identify the
unresolved claim, requested scope, missing evidence and usable existing artifacts.

## Evidence depends on the claim, not the niche

| Requested claim | Evidence to acquire | Insufficient substitute |
| --- | --- | --- |
| Recent or growing demand | Demand observations with measurement period and market | Fetch time; undated indices; views as search volume |
| Underserved or less competitive | Demand and comparable supply in the same subject/market; inspect how well samples answer the need | Content-gap labels or counts alone; absence from a small search as proof nobody serves it |
| Current, usable soundtrack | Dated audio trend evidence; scene relevance when requested | Old charts fetched today; titles as proof of sound, mood or usage rights |
| Repeatable reference format | Comparable channel history and content evidence of the format | Titles as proof the creator never appears on camera |
| Follow-up to a specific post | That post's identity, content and public feedback | An unrelated popular post; inferred private audience metrics |
| Unmet product demand | Market/search or buyer evidence and comparable existing offers | Social popularity as purchase intent; monetization eligibility as market research |

Do not impose these requirements on evergreen brainstorming, an explicit topic,
production-only guidance, or a first batch that does not request these claims.
Do not require absolute search volume if a dated demand proxy answers the ask.
Unknown revenue or approval status is not a new gate unless explicitly requested.
An unspecified region is a scope to disclose or clarify when material, not
permission to invent a market.

## Which Skill produces it

| Missing evidence | Skill that produces it |
| --- | --- |
| Dated trend or demand evidence for a platform | `research-youtube-trends`, `research-instagram-trends`, `research-tiktok-trends` |
| Comparable supply, competitor formats | `analyze-creator-competitors`, `analyze-tiktok-competitors` |
| The creator's own account history and profile | `review-creator-account` |
| One video's content, transcript, frames | `analyze-content-video` |
| Market, search-volume or buyer evidence | none in this release: a coverage gap |
| Product facts from a brand or product page | none: prep has no input for them, so a coverage gap |

A trend or competitor report without its `*_idea_context.json` projection is a missing source too:
name the producing Skill and its Idea projection step as the next step, and never write the
projection by hand.

## Bounded handling

1. Reuse validated evidence already in the workspace. Preserve the exact query, requested count
   and requirements; name only the missing evidence.
2. When a producing Skill exists, keep the request's required sources and let prep return the
   missing-source block, then name that Skill as the next step with the exact scope it should
   cover. Once its JSON output exists in the workspace, rerun this Skill in a new run with it.
   Ask the user only for identity or private access unresolved from context, not to transcribe
   public comments or copy results.
3. Separate independent needs. A completed demand collection can feed a bounded supply/content
   comparison; this is additional evidence, not a substitute for demand. Preserve URLs, period,
   market, sample size and unassessed dimensions. Inspect content before asserting quality or an
   on-camera format.
4. Deduplicate completed acquisitions. Repeatedly fetching the same stale chart or undated series cannot satisfy a missing field.
   Stop failed/unavailable paths, preserve their reasons and never silently swap sources. Retain
   usable partial rows with limitations rather than treating partial as either empty or complete.
5. No market capability means no coverage, not missing user effort. Return the precise capability
   gap; do not force a monetization study, use an unapproved network path or fabricate a
   successful market study.
6. Validate returned native artifacts and rerun the existing request decision. Keep required
   sources and fallback authorization intact. Attempted collection does not satisfy a source. Raw
   search lists or this handling are not a native TrendResearchReport/idea_context. Preserve
   unresolved claims in final output.

If a required claim remains unsupported, retain existing blocked/partial
semantics. Distinguish missing identity, no capability coverage, collection
failure and insufficient evidence. Usable content from independent successful
paths must not disappear because another collection failed.

Product and market evidence is a coverage gap for this Skill: it reads no web
pages and prep has no input for them. Record the gap rather than searching the
web or substituting a social-data source. Product facts the creator states
remain their statements: attribute them, and do not treat brand marketing as
clinical efficacy. A product display may omit unknown benefits without becoming
blocked.
For style, inspect relevant samples rather than more unrelated popular posts;
reject source-identity or transcript/frame-duration mismatches before projection.
A small inspected sample can support explicitly bounded adaptations without
claiming account-wide voice, algorithm knowledge or guaranteed sales.

## Reference creator voice and visual style

An account post list supplies sample URLs, not visual or spoken style. Reuse it
and select a small relevant sample spanning the requested format; respect any
historical cutoff. Timestamped transcript and keyframes for those samples come
from `analyze-content-video`; name it as the next step before declaring the
style unavailable. Its validated VideoAnalysis is the input (`--video-analysis`);
never hand-copy timestamps into upstream evidence. Unavailable full-video
understanding does not mean a transcript or frame path is unavailable.

Read actual frame pixels before describing framing, gestures or on-screen text.
Transcripts with recognition errors are not exact quotes or reliable brand names.
A silent/lip-synced/music sample cannot establish a creator's explanatory voice.
One clip can support a clip-level observation, not an account-wide habitual style.
Stop failed paths and keep the dimensions they leave unassessed. Do not replace
missing audiovisual evidence with another title search, infer private algorithm
signals, or promise virality/sales.

For products, reuse supplied materials and resolve exact brand/product identity
from them. Similar names and a same-brand catalog do not prove the formulation
or claim. Unknown product benefits can remain unclaimed
while drafting a routine demonstration; sales proof and guaranteed virality are
not additional input gates.
