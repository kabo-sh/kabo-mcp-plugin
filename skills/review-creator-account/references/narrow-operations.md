# Narrow operations

Each operation here is deterministic. Run only the one that matches the request and return its
native JSON with a short, bounded explanation. Do not run the complete synthesis or turn the result
into a Creator-facing Account Review unless the user asked for diagnosis, patterns or
recommendations. Commands use `<skill directory>` (the folder holding `SKILL.md`) and run from this
request's run directory; write inputs there with a heredoc.

## Analyzer operations

For a narrow request, run only the matching operation of `account_analyzers.py` on a supported
snapshot:

- `coverage`: whether the snapshot is sufficient.
- `baselines`: comparable-format personal medians.
- `rank`: content rankings and account-relative view multiples.
- `pillars`: performance by existing content classification; requires `--classification`.
- `funnel`: observable attention, interaction and action signals.
- `all`: the reusable `AccountAnalysis` of a complete review.

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/account_analyzers.py' snapshot.json --operation baselines --output personal_baselines.json
```

## Owner follower contribution

For a narrow owner request to rank content by follower contribution, never send `Follows` through
the view-ranked Account Analyzer and never ask a model to calculate ratios. Prepare a UTF-8 CSV or
`owner-follow-input.v1` JSON with one row per post and these canonical columns: `content_id`,
`published_at`, `follows`, and optionally `title`, `url`, `format`, `views`, `reach` and `group`. A
`normalized-social-snapshot.v1` owner export is also accepted directly. Preserve a missing metric
as blank; numeric zero is a real observation. Use the creator's requested window exactly:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/analyze_follow_contribution.py' owner_export.csv --window-start <inclusive-ISO-start> --window-end <inclusive-ISO-end> --output owner_follow_contribution.json
```

- `status: complete` means at least one observed Follows value is computable, including zero; it
  does not establish adequate coverage or support a content decision. Assess `coverage`, group
  sample sizes and paired-N against the requested comparison, without a universal sample threshold.
  Report supported facts and unresolved comparisons separately.
- Keep the three rankings separate: absolute Follows, Follows per 1,000 views, and Follows per
  1,000 reach. Preserve missing metrics and zero denominators. Compare groups using available-N,
  total and median Follows and paired ratio-of-sums efficiency; unequal coverage is not equal
  confidence.
- Observed contribution is not causal attribution. Return the native JSON with a bounded
  interpretation; run a complete review only if broader diagnosis or recommendations were requested.

## Engagement rate

Use `calculate_engagement_rate.py`. This never triggers a semantic synthesis or a complete review.

- **Supplied averages** (Instagram, TikTok or YouTube): write a manual input JSON with `platform`,
  `followers`, `average_likes`, `average_comments` and optional `average_views`. Set
  `request_surface` to `cross_platform_calculator` only when the user is explicitly comparing the
  same inputs under the selected platform benchmark; otherwise omit it. The input mode is
  `manual_averages`. YouTube `followers` means subscribers.
- **A public Instagram username**: one `get_research_capabilities` readiness call for this run
  first. Call `instagram_resolve_profile`, fetch and persist its Envelope as
  `references/complete-review.md` (*Placing Envelopes you fetch yourself*) says, and run the
  calculator with that profile. If it says the profile has fewer than six embedded calculable
  posts, call `instagram_list_posts`, persist its Envelope and rerun with `--content-envelope`. If
  it says the public profile requires `list_reels` because embedded posts have no play counts, call
  `instagram_list_reels` (and more `instagram_list_posts` pages if Feed is still short), persist
  those Envelopes and rerun with `--content-envelope` for every collected page. Stop when persisted
  Feed rows plus persisted Reels rows reach 100 combined; never page past that combined cap. Do not
  tell the user that public plays are unavailable until after that Reels retry. "Embedded timeline
  is sufficient" means at least six calculable posts **and** at least one play count; six likes or
  comments with `view_engagement_rate_percent=null` is not sufficient. The input mode is
  `public_profile`; likes and comments use medians across up to 50 deduplicated calculable posts,
  matching the public Instagram calculator contract.
- **TikTok**: for a narrow request, use supplied aggregate inputs. A complete public TikTok review
  uses the public account history; never use a public snapshot to infer private TikTok analytics.

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/calculate_engagement_rate.py' manual_input.json --output engagement_rate.json
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/calculate_engagement_rate.py' --profile-envelope snapshot/envelope-01.json --content-envelope snapshot/envelope-02.json --output engagement_rate.json
```

Reading the result:

- Both formulas count likes plus comments only. The follower rate is
  `(likes + comments) / followers * 100`; the optional view rate divides the same interactions by
  compatible average views. On Instagram and TikTok, apply a benchmark only to the follower rate and
  never invent a view-rate grade. On YouTube the calculator grades the view rate with a published
  view-rate band and leaves the subscriber rate numeric.
- Below 1,000 followers, still report both rates, but do not treat the follower-rate band as a
  cross-account verdict: the small denominator inflates the percentage. Prefer the view rate when
  views exist. Repeat any `limitations` from the JSON in the explanation.
- The default view rate uses the full sample. If
  `sensitivity.view_engagement_rate_excluding_highest_play_percent` is present, mention it as
  sensitivity only; never replace the default view rate with it.
- YouTube subscriber-rate letter grades have no verified public source here. For a YouTube ER band,
  run the calculator with `platform: youtube` and grade the **view** rate only, using a published
  True Engagement Rate band: under 2% needs work, 2–5% is good, above 5% is excellent. Our formula
  is likes plus comments only; that published band also counts shares. Never apply those bands to
  the subscriber rate. Numeric likes, comments and views already in the sample may still be
  reported. The Kabo Free Tools calculator has Instagram and TikTok bands only; this path is
  independent of that page.
- Return the native `engagement-rate.v1` JSON plus a short explanation of the two denominators.
