Write `report/craft-teardown.md` yourself; there is no renderer. The answer is prose shaped by the
creator's question in section 1, not by a schema or the timeline, and it writes no
`video_analysis.json`, `VIDEO_DIAGNOSIS.md` or creator result. Measurements come first, each with
the timecode it came from, before any judgement about why something works. Then run this one
command, which records when the teardown was finished and how long it is, and decides nothing:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/acv_timing.py answer --run '<run directory>' --answer report/craft-teardown.md
```

Then deliver the file's content to the creator.

The rules for what a teardown may claim, from `references/craft-teardown.md`:
