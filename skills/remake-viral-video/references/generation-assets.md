# Reusable person and voice materials

Use the tools' declared parameter schemas; identity and Chat origin are supplied by the host.
The product owns material eligibility, compatibility, revisions, storage and next actions. Never
construct a file ID, media link, account ID, candidate, quote or provider voice resource.

1. Read the existing product script to get its project ID, version, current video ID and exact
   spoken text. If the creator supplied complete approved words here and no project exists,
   use the existing `save_script` tool with `kind:"draft"`, a short topic and those exact words
   as `script_text`, then read the returned project with `list_scripts` in lookup mode. Saving
   the exact input for the requested video does not authorize a rewrite or a video charge. Do
   not save a second copy when that script already exists. If saving/reading is unavailable,
   say so and keep the direct input workflow; never invent a project or version. A source
   video's speaker is not automatically the creator.
2. Call `find_video_material_draft` for that script project before creating a draft. Resume a
   matching unfinished draft. If its frozen input differs from what the creator now requests,
   create one new draft with the exact approved input using `create_video_material_draft`.
   Keep the returned draft ID through account connection, page closure and retries.
3. Call `search_assets` for each missing role and the capability the video needs. Confirmed assets
   can be used without a currently connected account. For talking-head input, require person
   `presenter_video` and `voice_sample`; a `portrait_reference` alone cannot replace a speaking
   video. An explainer requires only voice. Only use the combinations the product accepts.
4. The creator chooses assets in the materials card. After an explicit request such as “use my
   saved voice”, `select_video_assets` can save that exact choice using IDs and revisions returned
   by Kabo. Preserve every other selection. If several assets could be meant, show the card and
   let the creator choose; do not infer identity or ownership from appearance or account binding.
5. Read `get_video_material_draft` and follow `nextAction`:

   | Action | Continue with |
   | --- | --- |
   | `select_assets` | The existing materials card; no binding prerequisite. |
   | `connect_account` | The card's account connection form; preserve the same draft. |
   | `prepare_from_account` | `prepare_account_assets` for that account and only `missingKinds`, with the draft ID and exact revision. |
   | `wait` | Say preparation continues in the background; end the turn. The card observes the same task. Do not keep the model polling. |
   | `review_candidates` | The card's actual portrait and voice previews, then individual confirmation by the creator. |
   | `supply_source` | The card's alternative owned video, upload or recording. Do not loop back to binding. |
   | `continue_generation` | The exact ready draft can proceed to its existing quote workflow. |

6. A candidate is not a saved asset. Let the creator see the actual portrait and listen to the
   actual voice, name each item and confirm their right to use it. The creator submits this in
   the same card in Chat or GUI; the agent cannot fill the confirmation checkbox or submit a
   consent boolean. Rejection, a closed card, silence, a generic “continue” before previews, or
   an account connection is not this consent. Read the same draft after they finish. Claim
   “saved” only for assets the product reports as saved. Keep a successful role when the other
   fails; prepare only missing roles. A recording is made by the creator through the card, never
   by the agent operating the camera.
7. When the creator wants to proceed and the draft is ready, call `create_video_from_assets` with
   its ID and exact revision, or let them continue in the card. Keep its returned `requestId`
   and the resulting production `jobId`. The production card observes preparation, presents the
   existing quote, and requires the creator's separate generation confirmation. Do not create a
   parallel remake, write alternative script files, silently select a paid model, or treat asset
   saving as approval of that quote. Inspect the existing production with the available task
   tools when asked for progress; say it started or finished only when its actual state says so.
8. For `draft_changed`, `result_changed` or binding changes, reread the same object and show its
   current choices; old candidate confirmation never applies to a new result. A retry is only
   for an explicit request and uses the existing preparation's `checkpointId`. If a write's
   outcome is unknown, read the original draft/preparation/request instead of creating a new
   one. At a limit, wait for the product's permitted action. If this deployment does not offer
   the capability, say it is unavailable; never fabricate a successful extraction or preview.

Signed previews belong in the authenticated materials card, not the transcript or model text.
Do not turn a material ID into a fake attachment. A saved audio sample is not proof that any
provider's voice model is trained, verified or ready. Archiving hides a new choice; revocation
prevents new execution. Never bypass either state by reusing an old temporary file ID.
