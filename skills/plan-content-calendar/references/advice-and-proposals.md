# Advice, reviews and proposals

Read this when the request is not (only) an artifact-backed calendar: strategy or restart advice, a
review of times the creator already stated, or a proposed plan for topics the creator supplied. None
of these routes reserves a run; only the cadence helper below is called, and it needs no run.

The request may arrive in any language; the examples below describe equivalent intent.

First distinguish advice, a fact-only schedule review, a proposed plan from supplied topics, and an artifact-backed execution calendar. For sustainable filming/editing workflows, restart guidance, content-role mix or a 100-video learning roadmap, return the strategy subtask to the host before demanding SelectedIdeas or finished media. Generic workflow advice may use stated assumptions; private account metrics are required only for account-specific diagnosis. Actual capacity claims need the Creator's time budget, and actual calendar slots still need selected content. Do not replace strategy with eight example slots or turn fixture content into the Creator's plan.

For advice, answer the requested strategy now instead of offering a routing menu such as generic versus personalized planning. Give a usable proposed cadence and review checkpoints from the supplied constraints; label unconfirmed capacity as an assumption. A missing account or private metrics blocks an account-specific diagnosis, not general restart guidance. Do not state algorithm penalties or recovery guarantees as facts without applicable evidence; a practical restart plan need not depend on deciding that claim.

For a review of already stated times, collisions or reminders, resolve what the brief establishes before asking for artifacts. Distinguish unnamed items with neutral labels, preserve every fixed commitment, show the requested window with unknown content left unfilled (without inventing recurring slots when cadence is unknown), and explain which conflicting items cannot proceed to reminders or publishing. Ask only for information needed to resolve the remaining uncertainty. Missing titles, media files or SelectedIdea artifacts do not prevent this advisory review; they still prevent claiming a validated native calendar or actionable handoff. Do not fabricate artifacts or confirmations to enter the native pipeline.

When the Creator supplies topics and asks you to design their angles, formats and posting dates, that request authorizes a proposed plan for those topics. Return the complete proposal with every supplied topic preserved, clearly labeling any proposed cadence or audience assumptions. An unspecified CTA is not a prerequisite for proposing a calendar. Do not turn these proposals into confirmed SelectedIdeas or claim native artifacts, reminders or publishing readiness. If a dated plan requires an unknown timezone or start date, deliver the supported relative order and ask only for the missing anchor; do not invent an exact instant. Binding or changing approved source artifacts remains subject to their own provenance rules.

Answer a proposed plan from supplied topics in the conversation, not through the native pipeline: do not reserve a run directory, write a content-calendar request or call any script for it. Without SelectedIdea artifacts that pipeline can only fail, and a failed run beside a usable draft reports the opposite of what happened. Title the proposal as an unvalidated draft, not a native calendar, and name what would make it one: the selected items and the account.

For all advice and proposed plans, preserve each applicable evidence limitation, safety or rights boundary, and production condition in the final answer beside the affected suggestion. When using upstream ideas, carry those constraints forward with their content. Distinguish a proposed schedule from confirmed production capacity. Reuse the existing upstream result rather than repeating research to write the summary; do not compress away a constraint that changes whether the suggestion is usable.

When a calendar also needs new ideas or holiday context, the host discovers relevant research/ideation, reuses known region and dates, and obtains content selection before materializing those slots. Unknown region affects holiday relevance, not whether a neutral date skeleton can be shown. Missing selections remain explicit unfilled slots. This skill never invents holiday facts or performs publishing.

A four-week horizon does not imply eight posts. Preserve the Creator-selected content set; do not expand, clone, or request new ideas just to fill every week. Use the declared cadence, and report unused slots or uneven distribution honestly. Missing cadence still requires clarification under the rule below. If only informal ideas are supplied, obtain the proper selected artifacts through the host; do not fabricate selection provenance or approve extra content.


## Plans built from account results

"Make a concrete 30-day plan from these results" after an account review is a proposed plan: the
creator supplied the account and the results, so deliver the dated draft now. Two things come from the
account, not from a default:

- **Cadence.** Use how often the account actually posts. Write the dated posts from the results to
  `posts.json` (`{"as_of": "<creator's today>", "posts": [{"published_at": "YYYY-MM-DD", "title": "<title or caption>"}]}`)
  and the draft's topics to `plan.json` (`{"days": 30, "topics": ["…"]}`), then run
  `python3 '<skill directory>/scripts/account_cadence.py' --posts posts.json --plan plan.json`.
  It returns posts per week over the last four weeks and the number of posts the window should hold.
  Plan that many and say the cadence follows their posting history. When it reports the cadence as
  unknown, ask once how often they post, or give the plan with the cadence labelled as an assumption.
  A creator's stated cadence ("at least one video a day") always wins.
- **No repeats.** Every topic must be new to the account. Replace each topic listed under
  `possible_duplicates` (it shares a specific subject with a published post) and run the check again;
  keep one only when the creator asked for a follow-up, and then name the earlier post. The check is a
  word-overlap screen, so also compare meanings yourself before delivering.
