# Scheduled three-window recommendation acceptance

This reference defines how to compare a scheduled recommendation implementation with this Skill.
It does not add a combined data tool, a new executable report route, or a call to Kabo's web agent.
Normal Skill requests keep the routes in SKILL.md. A combined backend result is not a validated
Skill report and must retain its own method version.

## One account, one fixed run

Freeze the actual platform account, effective profile, saved preferences, approved content languages,
exact UTC `as_of`, and the Skill source commit. Read a fresh effective profile for the next run;
freezing a run does not disable future profile updates. Missing profiles remain missing. Recent
zero posts alone do not invalidate an existing matching profile. Do not borrow a different account's
or platform's profile.

One scheduled run may build 24h, 7d and 30d lists from shared evidence. Keep targeted recall for
short windows, deduplicate full candidate evidence before judgment, and share identical detail
requests. Judge each unique candidate's niche and language from its original text and declared
language fields without views, dates, search rank or query in the judgment input. User consent to
broaden language changes only the language policy; it does not broaden the niche or time window.

Filter and rank each window independently using its exact publication timestamps. Never select
30d Top-N first and split that shortlist into shorter windows. A video may appear in several
windows; it may appear only once in each window. Preserve source URLs, original evidence,
judgments, rejection reasons, as_of and method version. Unknown publication dates, unknown
public views and failed required data calls are not zero values or successful empty retrieval.

A combined implementation must publish all three completed lists together. A failed required route
cannot be hidden by successful routes. Preserve failed and empty runs in comparison denominators.
A scheduled product may retain a prior unexpired list after failure, with its original as_of; that
fallback is not the failed run's new recommendation.

## Compare three distinct things

1. **Postprocessing:** the same frozen candidates, original judgment artifacts and exact window.
   This checks evidence projection, filtering, deduplication and ranking, not new model quality.
2. **Judgment:** the same frozen candidates and effective profile, with independent new judgments.
   Keep expected judgments, historical labels and original recommendation lists out of the new
   judgment input. Historical model labels are not independent human truth.
3. **End to end:** matched original Skill and backend executions, including actual retrieval and
   failures. Freeze the time anchor; record route, source, latency and cache differences. A historic
   report revalidation or replay is not a fresh end-to-end execution.

Compare by account and window: delivery and empty-result rate, niche/adjacent/off-niche share,
language mismatch, official-brand/sponsored content, own-account content, publication-window
violations, number delivered, source-link overlap and Good/Same/Bad with a short reason. Count
distinct displayed recommendations, not all eligible candidates or all repeated heat layers.
Record data API calls, provider requests, quota units and known data cost separately from model
usage. One three-window run has one shared task cost, not three copies of that cost. Unknown fees
remain unknown. Use measured costs rather than assuming a fixed savings ratio.

## Original-method boundary

The original short-window route applies to seven days or less. Its 30-day heat layer is not the
30-day long-window workflow. A backend extending short-window recommendations to 30 days must
record that method change and compare it with an actual original long-window run before claiming
equal or better quality. Do not silently change the original benchmark to the new method.

An archived 7d report provides no original 24h or 30d result. Keep unavailable comparisons explicit.
Use each report's original run ownership and validators; do not transplant artifacts into another
run, synthesize provider envelopes, or fetch data again to repair a missing local artifact.

For TikTok, short-window retrieval uses sort 0 and 1 for the exact provider date bucket and sort 1
for the 30d heat route, with local exact timestamps. A combined implementation can share identical
30d searches across windows. The original 30d workflow also includes its regional daily ranked
board and author history after the Gate. Follow `short-window.md` and `video-trend-workflow.md`;
a monthly heat result is not a replacement for that workflow.
