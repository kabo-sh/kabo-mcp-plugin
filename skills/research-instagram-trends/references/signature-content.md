# Signature content: a run with the Creator's saved account profile

Read this whole when `start` printed `creator profile: @… on instagram` and used it: with numbered
`signature content` lines, or with only the Creator's settings (excluded topics, a language or a
market they set). Its rules add to `references/request-and-query-plan.md`,
`references/discovery-and-gate.md` and `references/ranking-and-synthesis.md`; where they differ,
this file wins for this run. A run whose `start` printed no profile, or printed it as not used,
follows those references alone, and every command and call is the one they describe.

## Where the profile comes from

The profile is the complete `get_creator_profile` result for the Creator's linked Instagram account,
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

`--profile` and `--post` are two different starts: a supplied Reel names its own author as the
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
  retrieval label too, and their market only the default search region (Instagram search takes no
  region, so the market is not used here): never copy either into `locale`. Leave `locale` to what
  the user named.

## The query plan

Every intent belongs to one signature content item and carries one of that item's seed terms or
hashtags verbatim, written in the printed content language (when the language is not settled, in
the language of the item's own seeds). Across the intents, reach as many items as there are, up to
four; the caption-phrase floors of `references/request-and-query-plan.md` do not apply then. The
plan validator rejects an intent without a seed and names the items still missing. The Creator's
own seed words are what other creators of the same content caption with; a paraphrase in analyst
vocabulary retrieves a different pool.

Never put a topic the Creator excluded into an intent, with or without signature content: the plan
validator rejects one and names the topic.

## Discover

Each lane's `collect_instagram_trend_candidates` call also carries `"include": ["media_signals"]`:
each Reel then brings its audio id and title, whether the audio is original, and its duration. A
Reel without those fields is read as it is, and the run goes on without them.

If Kabo refuses a collect call only for its `include` parameter (an invalid-input error and no
data), do not retry it by hand: make the other calls of that hand-over as usual, then run the same
`discover` command with `--without-include` instead of `--placed`. It hands the refused calls over
once more without `include`; make them, then resume with `--placed` as usual.

`discover` then writes the eligible candidates of each lane
(`scripts/filter_candidate_eligibility.py`): it removes the Creator's own posts (those of removed
signature content items too), photo posts, the video format the Creator does not publish (180
seconds or less is short), ads, accounts outside 0.3–3 times the Creator's audience, and posts whose
hashtags or caption name a topic the Creator excluded (those are never topped back up); it keeps
every candidate it cannot judge, never removes one for its language, and tops a set under 20 back up
with the removed accounts closest in audience size. Every later stage reads that eligible set.

## The Gate

When the table's first line lists `subject.signature_content`, each line gets a fifth number at the
end: `<n> <topic_relevance> <locale_fit> <creator_transferability> <signature_content>` (that list
always comes with `subject.anchor_handle`). The fifth is an integer from 0 to the number of listed
entries; every other rule of the Gate file stays, for both lanes.

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

`rank` shares the items the enrichment returned across the signature content items before it
Analyzes (`scripts/allocate_signature_content.py`; with two lanes, over their union): each item
gets seats by its weight, at least one each, from the posts the Gate matched to it, ranked by their
account-relative multiple and plays, one post per account and spread over different sounds and
hashtags; the analysis reads them. An item without enough matching posts gives its seats to the
other items first, then to posts that matched none; seats nobody can fill stay empty and are never
padded. The enrichment call itself is unchanged.

## The synthesis

When the Analysis lists `signature_content` (each item with the seats it was given), cite at least
one post whose `ranked_content` row carries that item's `signature_content_id`, in
`featured_content_refs` or a pattern's `content_refs`, for every item whose `filled` is above 0;
the report validator rejects a report that leaves one out. The ranking stays as printed: the marks
only make sure each kind of content the Creator is known for is represented. When an item filled
fewer seats than its `quota`, note it briefly in `data_gaps`, never in Creator-facing prose, and
never make up the difference with posts that were not seated.
