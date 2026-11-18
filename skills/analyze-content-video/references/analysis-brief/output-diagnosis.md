Write `analysis/video_judgment.json` once, at its absolute run path, following the judgment schema
below: only these fields, with its shapes and enums. Keep `revisions` empty for `third_party` and
`unknown`. Cite exact refs from `analysis/content_evidence.references.json`; an observation resting
on a whole-video note uses `basis` `viewer_observation` and cites the note's id. The composer
supplies evidence lineage, completeness and the unchanged `analysis/deterministic.json` block.

Then check its references (a read-only step):

```sh
cd '<run directory>' && python3 <skill directory>/scripts/compose_video_analysis.py --check-judgment-refs --judgment analysis/video_judgment.json --evidence analysis/content_evidence.json --reference-index analysis/content_evidence.references.json
```

Advance only on `status: ready`, with one correction opportunity in total, as
`references/diagnosis-runtime.md` *The judgment* describes. Then print the view contract, read
`references/diagnosis-report.md` whole and write `analysis/creator_view.json` once:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/build_creator_result.py --print-view-contract --observations-from analysis/video_judgment.json
```

Check the view before the final step. The check runs every gate of the final step on scratch
copies, writes nothing and prints each violation with its field and limit:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/finish_diagnosis.py --run-dir '<run directory>' --check
```

On `needs_correction`, correct `analysis/creator_view.json` once for every violation listed (the
view's one correction; the judgment stays as saved) and run the check once more. Advance only on
`status: ready`; if it is still not ready, stop and report the gap. Then finish with the final
step; its deliverable is `report/VIDEO_DIAGNOSIS.md`, delivered as *Delivery* in `SKILL.md` says:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/finish_diagnosis.py --run-dir '<run directory>'
```

Judgment schema:
