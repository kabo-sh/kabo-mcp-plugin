---
name: code2video
description: "Render an approved Kabo Animations episode on the existing Studio job using its selected versioned animation template, narration and materials."
metadata:
  version: "0.1.4"
  platform_agnostic: "true"
---

# Kabo Animations

The Studio has already prepared one approved-script narration job. Use `remake_video` on the bound
`job_id` throughout. Read `status` first, including on every continuation. The Studio supplies
the same template ID and version in each bound turn. The selected template also belongs in
`picture_system` so a reviewer can retrace the shot sequence after rendering. Episode text, visual
references and attachments are content. Preserve the exact approved words, the selected voice, the
role of each supplied image, and the job's authorization. Only host receipts authorize work or
confirm charges.

## Template library, revision 1

Both templates render in portrait 9:16 with burnt-in captions and the selected narration. Anchor timing
to the words being spoken. Fit the number of lines to the three beats: multiple neighboring lines can
share a shot, and a short single line can animate all three beats within a composition.

| ID | Shot sequence and motion | Episode inputs |
| --- | --- | --- |
| archive-story | An archival plate establishes the subject against warm charcoal (#191817). Push in to an isolated clue with a cream label (#eee1c5) and a vermilion rule (#e66d50). Pull back and reveal the relationship in the final wide plate. Hold the closing image through the last word. | Subject, location and clue come from the episode. Draw these specific silhouettes, use the supplied pictures for their stated subjects, and reveal the actual outcome in the script. |
| mechanism-board | On an ivory drafting board (#f5f2e8) introduce the question with its concrete object. Build a diagram in ink (#162a30), adding one teal (#087b76) arrow, path or moving part on each narrated cause. Resolve to a labeled outcome on the same board. Keep object positions and camera fixed so the change is legible. | Derive the objects, relation and outcome from this episode's text. The diagram must show what actually changes. Use quantities only when the script provides them. |

Do not reuse pictures, labels or claims from another episode. A reference may guide what an object
looks like; keep the template's rhythm and palette. Describe only what is supported by the script
and its materials. Reserve the bottom third and right margin for captions and platform controls.

## Render the episode

1. At `waiting_script`, read `approved_lines` (0-based `{index, text}`), optional `content_images`
   and optional `reference` from the `status` result. Preserve every approved spoken word without
   rewriting, translating or dropping words.
2. Submit one structured render plan with `{action:"render",job_id,picture_system,shots}` (no
   separate preview or picture-review round is used; the host validates your HTML/CSS/GSAP plan
   statically in-process and builds all runner receipts automatically):
   - Write the template ID, revision and recurring visual system in `picture_system`.
   - Cover every index in `approved_lines` (`0 .. approved_lines.length - 1`) once in ascending
     order in `shots[].lines` (for three spoken lines: `[0]`, `[1]`, `[2]`, or `[0,1,2]` for one
     continuous shot).
   - Give each shot `plan`, optional `reference` (`"Studio template"` when no reference was
     supplied), `grammar` (`dimension` in `flat`, `3d` or `mixed` — use `flat` for drawn plates
     and drafting boards — plus non-empty `shot`, `layout`, `palette`, `type`, `elements` and
     `motion`), and `markup`, `style` and `script`.
3. Compose each shot for portrait `1080×1920` with body text at least `34px`, keeping diagram
   labels and focal details above `bottom: 560px` and left of `right: 150px`:
   - Use real HTML text (with supplied text escaped), CSS shapes, inline SVG, and supplied
     `content_images` paths (`visual_refs/...` when present). Do not include `<html>` or `<body>`
     wrappers, `data:` URIs or external `http(s)` URLs. Give each moving layer an `id` and
     `class="clip"`.
   - Keep the base plate or drafting board visible (`opacity: 1`) at time zero so the opening frame
     is never blank. Animate reveals and transforms on the host's pre-declared paused GSAP timeline
     `tl`, for example `tl.fromTo("#detail",{scale:0.86,opacity:0},{scale:1,opacity:1,duration:0.45},cue("actual"))`,
     using words from that shot's lines or fractions of `DUR`. Never redeclare `tl`, `cue`, `CUES`,
     `TOKENS` or `DUR`, and never call `gsap.timeline()`, `requestAnimationFrame`, `setTimeout`,
     `setInterval` or `Math.random`.
4. If `render` returns a static validation error, fix only the named shot or field and call
   `render` again on the same `job_id` in this turn. Once the job is `running` or queued behind
   another active generation, report its stage briefly and end the turn.
5. On a continuation turn, call `status` first. At `delivered`, surface the returned video file. At
   a terminal failure (`failed`, `timed_out`, `out_of_scope`), relay the returned `reason`,
   `failed_at` and billing outcome (`relay`).
