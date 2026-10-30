# Signature content: a run with the Creator's saved account profile

Read this whole when `start` printed `creator profile: @… on youtube` and used it: with numbered
`signature content` lines, or with only the Creator's settings (excluded topics, a language or a
market they set). Its rules add to `references/video-trend-workflow.md`; where the two differ, this
file wins for this run. A run whose `start` printed no profile, or printed it as not used, follows
the workflow reference alone, and every command and call is the one it describes.

## Where the profile comes from

The profile is the complete `get_creator_profile` result for the Creator's linked YouTube channel,
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

`--profile` and `--video` are two different starts: a supplied video names its own channel as the
Creator, the profile names the channel it was read for. `start` refuses both together.

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
  channel's handle; a different handle stops `discover`. A channel id is never compared with a
  handle.
- Never write `content_language`, `accepted_languages`, `audience_count`, `formats`,
  `signature_content`, `excluded_topics`, `market_region`, `own_content_ids` or `profile_basis` into
  the Request yourself: `discover` copies them from the profile file before it freezes the window,
  and removes them when there is no profile file.
- The content language is a retrieval label, not a market and not a filter: never copy it into
  `locale.language`, which the Gate scores `locale_fit` against. A language the Creator set is a
  retrieval label too, and their market only the default search region (the collect call's region
  when `locale.region` is empty, never its language): never copy either into `locale`. Leave
  `locale` to what the user named.

## The query plan

Every intent belongs to one signature content item and carries one of that item's seed terms or
hashtags verbatim, written in the printed content language (when the language is not settled, in the
language of the item's own seeds). The two intents go to the first two printed items (the main one,
then the heaviest), one each; with one item, both go to it. This replaces the workflow reference's
split between the source's own wording and the format's common name; the length rules stay (a seed
in a script written without spaces is matched inside the query with its spaces removed). `discover`
passes `--request` to the plan validator, which rejects an intent without a seed and names the seeds
to copy. The Creator's own seed words are what other creators of the same content title with; a
paraphrase in analyst vocabulary retrieves a different pool.

Never put a topic the Creator excluded into an intent, with or without signature content: the plan
validator rejects one and names the topic.

## Discover

The collection call is unchanged, except that it carries the Creator's market as its region when
`locale.region` is empty. After coverage passes, `discover` writes the eligible candidates
(`scripts/filter_candidate_eligibility.py`) from the channel and duration each candidate came back
with: it removes the Creator's own videos (those of removed signature content items too), the video
format the Creator does not publish (180 seconds or less is a Short), channels outside 0.3–3 times
the Creator's audience where a count is known, and videos whose title or hashtags name a topic the
Creator excluded (those are never topped back up); it keeps every candidate it cannot judge (a
candidate without a duration stays), never removes one for its language, and tops a set under 20
back up with the removed channels closest in audience size. Every later stage reads that eligible
set.

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

`rank` shares the videos the enrichment returned across the signature content items before it
Analyzes (`scripts/allocate_signature_content.py`): each item gets seats by its weight, at least
one each, from the videos the Gate matched to it, ranked by their channel-relative breakout
multiple and views, one video per channel and spread over different hashtags; the analysis reads
them. An item without enough matching videos gives its seats to the other items first, then to
videos that matched none; seats nobody can fill stay empty and are never padded. The enrichment
call itself is unchanged.

## The synthesis

When the Analysis lists `signature_content` (each item with the seats it was given), cite at least
one video whose `ranked_content` row carries that item's `signature_content_id`, in
`featured_content_refs` or a pattern's `content_refs`, for every item whose `filled` is above 0;
the report validator rejects a report that leaves one out. The ranking stays as printed: the marks
only make sure each kind of content the Creator is known for is represented. When an item filled
fewer seats than its `quota`, note it briefly in `data_gaps`, never in Creator-facing prose, and
never make up the difference with videos that were not seated.
