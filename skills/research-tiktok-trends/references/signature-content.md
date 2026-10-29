# Signature content: a run with the Creator's saved account profile

Read this whole when `start` printed `creator profile: @… on tiktok` and used it: with numbered
`signature content` lines, or with only the Creator's settings (excluded topics, a language or a
market they set). Its rules add to `references/video-trend-workflow.md`; where the two differ, this
file wins for this run. A run whose `start` printed no profile, or printed it as not used, follows
the workflow reference alone, and every command and call is the one it describes.

## Where the profile comes from

The profile is the complete `get_creator_profile` result for the Creator's linked TikTok account,
read with `"include": ["content_profile"]` and `"effective": true` (once more without `effective`
when Kabo refuses the read only for it) and saved unchanged as a file. When the file carries
`effectiveContentProfile`, the profile with the user's own edits applied by Kabo, and the scripts
know its version, they read that; otherwise `contentProfile`. The scripts read either that complete
result or its `structuredContent` object, and refuse an error result. Never write, merge, trim or
edit a profile file, and never rebuild one from what a tool displayed: a tidied seed word retrieves
nothing, and a guessed language turns a search label into a filter. Without a saved profile there is
no `--profile`; plan exactly as without one.

The saved profile already carries the edits the user made (renamed, removed or merged signature
content, which one is main, excluded topics, a language or market they set): use it as it is. Never
type a correction the user states in this conversation into the Request or the profile file. To save
one, follow `references/profile-edits.md`; it applies from the next run, because `start` refuses a
different profile file for the same run.

`--profile` and `--video` are two different starts: a supplied video names its own author as the
Creator, the profile names the account it was read for. `start` refuses both together.

`start` copies the file into the run as `creator-profile-source.json` and prints, after the schemas,
the profile's content language, accepted languages, formats and numbered signature content items
(the main one first, marked `main`), each with its name, topic, approach and seed terms or hashtags,
then any topics the Creator excluded, the market they set and the edits that no longer match the
current profile (those are not applied). A profile for another platform, or one with neither
signature content nor a setting of the Creator's, is printed as not used and the run plans exactly
as without one. One with settings but no signature content plans as without signature content and
keeps those settings.

## The Request

- Leave `creator_profile.handle` out (`discover` fills in the profile's) or write that same
  account's handle; a different handle stops `discover`.
- Never write `content_language`, `accepted_languages`, `audience_count`, `formats`,
  `signature_content`, `excluded_topics`, `market_region`, `own_content_ids` or `profile_basis` into
  the Request yourself: `discover` copies them from the profile file before it freezes the window,
  and removes them when there is no profile file.
- The content language is a retrieval label, not a market and not a filter: never copy it into
  `locale.language`, which the Gate scores `locale_fit` against. A language the Creator set is a
  retrieval label too, and their market only the default search region (with no Request region and
  no `--region`, every call carries the market as its region): never copy either into `locale`.
  Leave `locale` to what the user named.

## The query plan

Every intent belongs to one signature content item and carries one of that item's seed terms or
hashtags verbatim, written in the printed content language (when the language is not settled, in the
language of the item's own seeds). The two intents go to the first two printed items (the main one,
then the heaviest), one each; with one item, both go to it. This replaces the workflow reference's
split between the source's own wording and the format's common name. `discover` passes `--request`
to the plan validator, which rejects an intent without a seed and names the seeds to copy. The
Creator's own seed words are what other creators of the same content caption with; a paraphrase in
analyst vocabulary retrieves a different pool.

Never put a topic the Creator excluded into an intent, with or without signature content: the plan
validator rejects one and names the topic.

## Discover

Every `tiktok_discovery_search_videos` call the stage hands over also carries
`"include": ["content_signals"]`: each row then brings its language, hashtags, duration, ad flag,
sound and the platform's own description of the video. A row without those fields is read as it
is, and the run goes on without them.

If Kabo refuses a search only for its `include` parameter (an invalid-input error and no data),
do not retry it by hand: make the other calls of that hand-over as usual, then run the same
`discover` command with `--without-include` instead of `--placed`. It hands the refused calls over
once more without `include`; make them, then resume with `--placed` as usual. Later searches in the
run go out without `include` on their own.

`discover` then writes the eligible candidates (`scripts/filter_candidate_eligibility.py`): it
removes the Creator's own posts (those of removed signature content items too), photo posts, the
video format the Creator does not publish (180 seconds or less is short), ads, accounts outside
0.3–3 times the Creator's audience, and posts whose hashtags, title or caption name a topic the
Creator excluded (those are never topped back up); it keeps every candidate it cannot judge, never
removes one for its language, and tops a set under 20 back up with the removed accounts closest in
audience size. Every later stage reads that eligible set.

## The Gate

When the table's first line lists `subject.signature_content`, each line gets a fifth number at the
end: `<n> <topic_relevance> <locale_fit> <creator_transferability> <signature_content>` (that list
always comes with `subject.anchor_handle`). The fifth is an integer from 0 to the number of listed
entries; every other rule of the Gate file stays.

- `signature_content`: the `number` of the entry whose approach this item reproduces, judged from
  that entry's `name`, `topic`, `approach` and `examples`, or 0 when it reproduces none. Write the
  number, never an id or a name, and pick the single closest entry. With that list present,
  `topic_relevance` asks whether the item reproduces the approach of one of those entries, in the
  same bands.
- Text after `platform summary, not by the author:` was written by the platform, not by the item's
  author. Use it to see what the item shows; never read it as the author naming a mechanism or as
  the author's wording.

When the table's first line lists `subject.excluded_topics` (topics the Creator excluded), with or
without signature content, `topic_relevance` is 0 for an item whose subject is one of them, however
it is worded and in whatever language.

## Rank

`rank` shares the recommendation across the signature content items: the shortlist gives each
item seats by its weight, at least one each, from the posts the Gate matched to it, and keeps one
post per account; the baselines add each account's shrunk multiple, which pulls a baseline built
from few posts toward the round's typical account. `scripts/allocate_signature_content.py` then
fills the final seats with the same seat rule, ranking each item's posts by their account-relative
multiple and plays and spreading them over different accounts, sounds and hashtags, and the
analysis reads them. An item without enough matching posts gives its seats to the other items
first, then to posts that matched none; seats nobody can fill stay empty and are never padded.

## The synthesis

When the Analysis lists `signature_content` (each item with the seats it was given), cite at least
one post whose `ranked_content` row carries that item's `signature_content_id`, in
`featured_content_refs` or a pattern's `content_refs`, for every item whose `filled` is above 0;
the report validator rejects a report that leaves one out. The ranking stays as printed: the marks
only make sure each kind of content the Creator is known for is represented. When an item filled
fewer seats than its `quota`, note it briefly in `data_gaps`, never in Creator-facing prose, and
never make up the difference with posts that were not seated.
