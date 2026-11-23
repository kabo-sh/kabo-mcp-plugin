"""Time-limit regression for local-file frame extraction and measurement (analyze-content-video/scripts/extract_local_frames.py).

In production a single command on a 4 vCPU host has a hard 60-second limit. The old version crammed measurement
and frame extraction into one command, and the measurement decoded the whole video three times at full
resolution; large files always timed out, the host received nothing, and the frames already extracted were lost
with it. These tests pin the fix: measurement runs two passes, each decoding only the stream it reads; the
command stops itself at --deadline-s and writes the results it has; frames are written to disk before
measurement; --signals-only measures on its own.
The mock cases do not depend on the media toolchain; the end-to-end cases are skipped on machines without
ffmpeg/ffprobe.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "analyze-content-video" / "scripts" / "extract_local_frames.py"
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def load() -> object:
    spec = importlib.util.spec_from_file_location("extract_local_frames", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MeasurementPassTest(unittest.TestCase):
    """What production showed: three full-resolution decodes of a 186 MB file did not fit in the
    minute a host allows one command, and the host kept nothing -- not even frames already written.
    These pin the cure without needing a media toolchain: two passes, each decoding only what it
    reads, and a pass stopped at the deadline kept as far as it got."""

    def setUp(self) -> None:
        self.module = load()
        self.calls: list[list[str]] = []

    def fake_tool(self, outcomes):
        def run(name, args, timeout):
            self.calls.append([name, *args])
            outcome = outcomes[len(self.calls) - 1]
            if isinstance(outcome, BaseException):
                raise outcome
            return subprocess.CompletedProcess([name, *args], 0, "", outcome)
        return run

    def measure(self, outcomes, has_audio=True, deadline_in=60.0):
        clock = types.SimpleNamespace(monotonic=lambda: 1000.0)
        with mock.patch.object(self.module, "run_tool", self.fake_tool(outcomes)), \
                mock.patch.object(self.module, "tool_version", lambda name: "ffmpeg test"), \
                mock.patch.object(self.module, "time", clock):
            return self.module.measure_signals(Path("/clips/cut.mp4"), 60.0, has_audio, 1000.0 + deadline_in)

    def test_sound_and_picture_are_each_decoded_once_and_only_what_they_read(self) -> None:
        signals, steps, _ = self.measure([
            "[silencedetect] silence_start: 2\n[silencedetect] silence_end: 3 | silence_duration: 1\n",
            "lavfi.scd.time: 4.2\nlavfi.freezedetect.freeze_start: 10\nlavfi.freezedetect.freeze_end: 12\n",
        ])
        self.assertEqual(2, len(self.calls), "one sound pass and one picture pass, not three decodes")
        sound, picture = self.calls
        self.assertIn("-vn", sound)
        self.assertEqual("0:a:0", sound[sound.index("-map") + 1])
        self.assertNotIn("-vf", sound)
        self.assertLess(sound.index("-vn"), sound.index("-i"), "-vn must stop the picture being read")
        self.assertIn("-an", picture)
        self.assertLess(picture.index("-an"), picture.index("-i"))
        self.assertEqual("0:v:0", picture[picture.index("-map") + 1])
        chain = picture[picture.index("-vf") + 1]
        # Reduced first, then both detectors on the same decoded frames.
        self.assertTrue(chain.startswith("fps=10,scale="), chain)
        self.assertLess(chain.index("scale="), chain.index("scdet="))
        self.assertIn("scdet=threshold=15", chain)
        self.assertIn("freezedetect=n=-60dB:d=1", chain)
        for call in self.calls:
            self.assertIn("-progress", call)
        self.assertEqual(["shots", "silence", "freeze"], signals["measured"])
        self.assertEqual([4.2], signals["shots"]["cuts_at_s"])
        self.assertEqual([{"start_s": 10.0, "end_s": 12.0, "duration_s": 2.0}], signals["freeze"]["spans"])
        self.assertEqual(["measure_silence", "measure_shots_and_freeze"], [step["operation"] for step in steps])
        self.assertNotIn("measured_until_s", signals)

    def test_a_file_without_sound_skips_the_sound_pass_and_says_why(self) -> None:
        signals, steps, notes = self.measure(["lavfi.scd.time: 4.2\n"], has_audio=False)
        self.assertEqual(1, len(self.calls))
        self.assertIn("-an", self.calls[0])
        self.assertEqual(["shots", "freeze"], signals["measured"])
        self.assertEqual(["silence"], signals["unavailable"])
        self.assertTrue(any("no audio track" in note for note in notes))
        self.assertFalse(any("could not be taken" in note for note in notes),
                         "a file with no sound is not a measurement that failed")

    def test_a_pass_stopped_at_the_deadline_keeps_what_it_read(self) -> None:
        stopped = subprocess.TimeoutExpired(
            ["ffmpeg"], 30,
            output=b"frame=10\nout_time_us=20000000\nprogress=continue\nout_time_us=24000000\n",
            stderr=(b"lavfi.scd.time: 4.2\nlavfi.freezedetect.freeze_start: 22\n"
                    b"lavfi.scd.time: 25.1\nlavfi.scd.ti"))
        signals, steps, notes = self.measure(["", stopped])
        self.assertEqual(["shots", "silence", "freeze"], signals["measured"])
        # The detectors had reached 25.1s although progress last said 24s; the cut-off line is dropped.
        self.assertEqual({"shots": 25.1, "freeze": 25.1}, signals["measured_until_s"])
        self.assertEqual([4.2, 25.1], signals["shots"]["cuts_at_s"])
        self.assertEqual(25.1, signals["shots"]["shots"][-1]["end_s"])
        self.assertEqual([{"start_s": 22.0, "end_s": 25.1, "duration_s": 3.1}], signals["freeze"]["spans"])
        self.assertEqual("completed_partial", steps[-1]["status"])
        self.assertIn("25.1s", steps[-1]["note"])
        note = next(text for text in notes if "Cuts and held frames" in text)
        self.assertIn("first 25.1s of 60.0s", note)
        self.assertIn("unmeasured, not as found to have none", note)

    def test_a_pass_with_no_time_left_is_not_started_and_reads_as_unread(self) -> None:
        signals, steps, notes = self.measure([], deadline_in=0.5)
        self.assertEqual([], self.calls)
        self.assertEqual(["shots", "silence", "freeze"], signals["unavailable"])
        self.assertEqual({"failed"}, {step["status"] for step in steps})
        note = next(text for text in notes if "time ran out" in text)
        self.assertIn("unread rather than as measured-and-found-nothing", note)

    def test_a_stopped_pass_that_read_nothing_is_unavailable(self) -> None:
        stopped = subprocess.TimeoutExpired(["ffmpeg"], 30, output=b"out_time_us=N/A\n", stderr=b"")
        signals, _, _ = self.measure(["", stopped])
        self.assertEqual(["silence"], signals["measured"])
        self.assertEqual(["shots", "freeze"], signals["unavailable"])

    def test_progress_lines_give_the_furthest_second(self) -> None:
        self.assertEqual(0.0, self.module.progress_seconds("out_time_us=N/A\n"))
        self.assertEqual(12.5, self.module.progress_seconds("out_time_us=3000000\nout_time_us=12500000\n"))


class DeadlineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load()

    def test_frames_out_of_time_are_skipped_opening_and_close_first(self) -> None:
        """Out of time is treated like out of bytes: the hook and the ending are already written."""
        plan = self.module.plan_frames(20.0, 3.0, 1.0, 2, 600)
        written: list[float] = []

        def run(name, args, timeout):
            target = Path(args[-1])
            target.write_bytes(b"jpeg")
            written.append(float(args[args.index("-ss") + 1]))
            return subprocess.CompletedProcess(args, 0, "", "")

        ticks = iter([0.0] * 8 + [99.0] * 100)  # eight frames fit, then the time is gone
        clock = types.SimpleNamespace(monotonic=lambda: next(ticks))
        with mock.patch.object(self.module, "run_tool", run), \
                mock.patch.object(self.module, "tool_version", lambda name: "ffmpeg test"), \
                mock.patch.object(self.module, "file_digest", lambda path: "0" * 64), \
                mock.patch.object(self.module, "time", clock):
            step, items, skipped = self.module.extract(Path("/clips/cut.mp4"), Path(tempfile.mkdtemp()),
                                                       plan, "cut", 3, deadline=10.0)
        self.assertEqual(8, len(items))
        self.assertIn(plan["closing_frame_s"], [item["t_seconds"] for item in items])
        self.assertEqual(plan["hook_frames"], sum(1 for item in items if item["t_seconds"] <= 3.0))
        self.assertTrue(skipped)
        self.assertEqual({self.module.TIME_BUDGET_REASON}, {entry["reason"] for entry in skipped})
        self.assertEqual("completed_partial", step["status"])

    def test_a_measurement_that_dies_leaves_the_frames_on_disk(self) -> None:
        """The artifact is written before measuring starts. Simulate the measurement being killed
        mid-way and check the frames were already delivered."""
        folder = Path(tempfile.mkdtemp())
        media = folder / "cut.mp4"
        media.write_bytes(b"not really a video")
        artifact = folder / "analysis" / "local-media.json"

        def run(name, args, timeout):
            if args[-1] == "-":
                # A decode to the null muxer (the shot-start pass) writes no file: none is faked here, or the
                # mock would leave a file named "-" in the working directory.
                return subprocess.CompletedProcess(args, 0, "", "")
            target = Path(args[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"jpeg")
            return subprocess.CompletedProcess(args, 0, "", "")

        def killed(*_args, **_kwargs):
            raise KeyboardInterrupt("stopped from outside")

        probe = ({"step": "local_extraction", "operation": "probe_media", "tool": "ffprobe",
                  "tool_version": "ffprobe test", "invocation_sha256": "x", "started_at": "t",
                  "status": "completed"},
                 {"format": {"duration": "6"}, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]})
        argv = ["extract_local_frames.py", "--media", str(media), "--out-dir", str(folder / "analysis" / "frames"),
                "--artifact", str(artifact), "--measure-signals"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(self.module, "probe", lambda path: probe), \
                mock.patch.object(self.module, "run_tool", run), \
                mock.patch.object(self.module, "tool_version", lambda name: "ffmpeg test"), \
                mock.patch.object(self.module, "measure_signals", killed):
            with self.assertRaises(KeyboardInterrupt):
                self.module.main()
        document = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual("available", document["frames"]["status"])
        self.assertTrue(document["frames"]["items"])
        self.assertNotIn("signals", document["media"])
        for item in document["frames"]["items"]:
            self.assertTrue((artifact.parent / item["path"]).is_file())

    def test_contact_sheets_share_the_byte_cap_with_the_frames(self) -> None:
        """A sheet carries about its four frames' bytes, so a sheet past what the frames left is not kept."""
        folder = Path(tempfile.mkdtemp())
        items = [{"_file": f"f{index}.jpg", "frame_id": f"cut#{index}", "t_seconds": index * 0.5} for index in range(10)]

        def run(name, args, timeout):
            Path(args[-1]).write_bytes(b"jpeg")
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(self.module, "run_tool", run), \
                mock.patch.object(self.module, "tool_version", lambda name: "ffmpeg test"):
            sheets, step = self.module.contact_sheets(items, folder, 3, deadline=float("inf"), byte_room=6)
        self.assertEqual(1, len(sheets))
        self.assertEqual([0.0, 0.5, 1.0, 1.5], [tile["t_seconds"] for tile in sheets[0]["tiles"]])
        self.assertEqual(("completed_partial", self.module.BYTE_BUDGET_REASON), (step["status"], step["note"]))
        self.assertEqual(["sheet-01.jpg"], sorted(path.name for path in folder.iterdir()))

    def test_a_deadline_must_be_positive(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(SCRIPT), "--out-dir", "o", "--artifact", "a.json",
             "--deadline-s", "0"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(2, result.returncode)
        self.assertIn("--deadline-s positive", result.stderr)

    def test_signals_only_does_not_need_a_frame_directory_but_frames_do(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(SCRIPT), "--artifact", "a.json"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(2, result.returncode)
        self.assertIn("--out-dir is required", result.stderr)


class SamplingRuleTest(unittest.TestCase):
    """The local plan is the connector's duration_scaled_v1 plan: the same frames for the same duration, cuts and
    windows, in the same budget order."""

    def setUp(self) -> None:
        self.module = load()

    def plan(self, duration, budget=120, **options):
        return self.module.plan_frames(duration, 3.0, 1.0, 2, budget, **options)

    def test_the_default_plan_matches_the_server(self) -> None:
        plan = self.plan(30.0)
        times, kinds = plan["_timestamps"], plan["_kinds"]
        self.assertEqual([0.0, 0.5, 1.0, 1.5, 2.0, 2.5], [at for at, kind in zip(times, kinds) if kind == "hook"])
        self.assertEqual([28.0, 28.5, 29.0, 29.5], [at for at, kind in zip(times, kinds) if kind == "closing"])
        self.assertEqual([float(second) for second in range(3, 28)],
                         [at for at, kind in zip(times, kinds) if kind == "body"])
        self.assertEqual((35, 28.0, False), (plan["frames"], plan["closing_frame_s"], plan["body_degraded"]))
        self.assertNotIn("include_shot_starts", plan, "no options asked for: the standard plan, unchanged")
        short = self.plan(2.0)
        self.assertEqual([0.0, 0.5, 1.0, 1.5], short["_timestamps"])
        self.assertEqual({"hook"}, set(short["_kinds"]))
        long = self.plan(600.0)
        self.assertEqual(120, long["frames"])
        self.assertTrue(long["body_degraded"])
        self.assertEqual(6, long["hook_frames"])

    def test_shot_starts_sit_just_after_a_cut_and_dedupe_against_higher_priority_frames(self) -> None:
        plan = self.plan(30.0, cuts=[0.3, 10.0, 10.1, 15.5, 29.9])
        pairs = list(zip(plan["_timestamps"], plan["_kinds"]))
        shots = [at for at, kind in pairs if kind == "shot_start"]
        # 0.35 is within 0.25s of the hook frame at 0.5 and 10.15 within 0.25s of the shot at 10.05: both dropped.
        # 29.95 is 0.45s from the closing frame at 29.5, so it stays.
        self.assertEqual([10.05, 15.55, 29.95], shots)
        self.assertEqual(2, plan["dropped_as_duplicate"]["shot_start"])
        body = [at for at, kind in pairs if kind == "body"]
        self.assertNotIn(10.0, body, "a body point within 0.25s of a shot start is skipped")
        self.assertIn(16.0, body, "0.45s from the shot start at 15.55 is far enough")
        self.assertEqual("detected", plan["shot_detection"]["status"])
        self.assertEqual(["hook", "closing", "shot_start", "dense_window", "body"], plan["budget_priority"])

    def test_dense_windows_keep_their_density_and_thin_by_a_whole_factor_over_budget(self) -> None:
        window = {"start_s": 0.0, "end_s": 5.0, "interval_s": 0.25}
        plan = self.plan(30.0, cuts=[], dense_windows=[window])
        dense = [at for at, kind in zip(plan["_timestamps"], plan["_kinds"]) if kind == "dense_window"]
        self.assertIn(0.25, dense)
        self.assertNotIn(0.5, dense, "the hook frame at 0.5 keeps its place")
        self.assertEqual(plan["dense_window_frames"], len(dense))
        tight = self.plan(30.0, budget=20, cuts=[], dense_windows=[window])
        # Six hook and four closing frames leave ten: 0.25s does not fit, 0.5s does (its points on the hook are
        # duplicates), and the body point at 3.0 beside the dense frame there is skipped without its slot coming back.
        self.assertEqual(0.5, tight["dense_windows"][0]["interval_s"])
        self.assertEqual([3.0, 3.5, 4.0, 4.5],
                         [at for at, kind in zip(tight["_timestamps"], tight["_kinds"]) if kind == "dense_window"])
        self.assertEqual(19, tight["frames"])

    def test_over_budget_the_order_is_opening_closing_shot_starts_dense_windows_body(self) -> None:
        cuts = [3.0 + index * 0.5 for index in range(400)]
        plan = self.plan(300.0, cuts=cuts, dense_windows=[{"start_s": 100.0, "end_s": 110.0, "interval_s": 0.5}])
        counts = {kind: plan["_kinds"].count(kind) for kind in self.module.BUDGET_PRIORITY}
        self.assertEqual({"hook": 6, "closing": 4, "shot_start": 110, "dense_window": 0, "body": 0}, counts)
        self.assertGreater(plan["dropped_for_budget"]["shot_start"], 0)
        self.assertEqual("budget", plan["dense_windows"][0]["ignored"])
        self.assertTrue(plan["body_degraded"])
        order = self.module.extraction_order(plan["_kinds"])
        self.assertEqual(["hook"] * 6 + ["closing"] * 4, [plan["_kinds"][index] for index in order[:10]])

    def default_plan(self, duration, cuts=(), budget=120):
        """What both ends sample by default: the standard plan plus the default window (the first 50s every 0.5s)."""
        return self.plan(duration, budget=budget, cuts=list(cuts),
                         dense_windows=self.module.select_method.with_default_window([]))

    def test_the_default_window_and_the_body_split_the_budget(self) -> None:
        """Both ends, by default: the first 50s every 0.5s while the windows may take the budget the body outside them
        does not need, at most half of it otherwise (stretched by a whole factor to fit); the body only over time no
        window covers, so no slot is spent inside a window; degraded only where that time is sparser than 1s."""
        def grid(until, step=0.5):
            return [index * step for index in range(int(until / step))]

        def body(plan):
            return [at for at, kind in zip(plan["_timestamps"], plan["_kinds"]) if kind == "body"]

        # 20s and 50s: the window covers the whole video, every frame sits on the 0.5s grid, nothing is degraded.
        short = self.default_plan(20.0)
        self.assertEqual(grid(20.0), short["_timestamps"])
        self.assertEqual((40, False, 0), (short["frames"], short["body_degraded"], short["body_frames"]))
        self.assertEqual([{"start_s": 0.0, "end_s": 20.0, "requested_interval_s": 0.5, "interval_s": 0.5, "frames": 30,
                           "clipped": True, "ignored": None}], short["dense_windows"])
        whole = self.default_plan(50.0)
        self.assertEqual(grid(50.0), whole["_timestamps"])
        self.assertEqual((100, False, 0), (whole["frames"], whole["body_degraded"], whole["body_frames"]))
        # 90s: the body after 50s needs 38 of the 110 frames left, so the window gets 72 at most; 94 do not fit, so it
        # is stretched to 1s (47). The body then runs every 1s from 50s to the closing band, and nothing is degraded.
        mid = self.default_plan(90.0)
        self.assertEqual((1.0, 47), (mid["dense_windows"][0]["interval_s"], mid["dense_window_frames"]))
        self.assertEqual([float(second) for second in range(50, 88)], body(mid))
        self.assertEqual((95, 1.0, False), (mid["frames"], mid["body_interval_s"], mid["body_degraded"]))
        # 10 minutes: the window keeps half (47 at 1s), the other half spreads over 50s..598s, which is degraded.
        long = self.default_plan(600.0)
        self.assertEqual((119, 47, 62, 8.699, True), (long["frames"], long["dense_window_frames"], long["body_frames"],
                                                     long["body_interval_s"], long["body_degraded"]))
        self.assertEqual(50.0, body(long)[0])
        self.assertTrue(all(at >= 50.0 for at in body(long)), "no body slot inside the window")

    def test_shot_starts_come_before_the_windows_which_thin_by_a_whole_factor(self) -> None:
        cuts = [50.0 + index * 0.6 for index in range(60)]
        plan = self.default_plan(90.0, cuts=cuts)
        self.assertEqual(60, plan["shot_start_frames"])
        window = plan["dense_windows"][0]
        # 50 frames left after the cuts; the body outside the window needs 38, so the window gets half (25): 2s.
        self.assertEqual((0.5, 2.0, 23, None), (window["requested_interval_s"], window["interval_s"], window["frames"],
                                                window["ignored"]))
        self.assertEqual((98, True), (plan["frames"], plan["body_degraded"]))

    def test_windows_are_taken_in_order_each_whole_or_not_at_all(self) -> None:
        # The connector's rule: after the common stretch, a window that still does not fit is ignored whole and a
        # later one that fits is still laid.
        first = {"start_s": 10.0, "end_s": 12.0, "interval_s": 0.5}
        second = {"start_s": 20.0, "end_s": 20.5, "interval_s": 0.5}
        plan = self.plan(30.0, budget=12, cuts=[], dense_windows=[first, second])
        self.assertEqual([1, 0], [window["frames"] for window in plan["dense_windows"]])
        self.assertEqual([None, "budget"], [window["ignored"] for window in plan["dense_windows"]])
        outside = self.plan(30.0, cuts=[], dense_windows=[{"start_s": 40.0, "end_s": 45.0, "interval_s": 0.5}])
        self.assertEqual("outside_duration", outside["dense_windows"][0]["ignored"])

    def test_the_body_skips_the_windows_and_runs_one_grid_per_uncovered_stretch(self) -> None:
        plan = self.plan(60.0, cuts=[], dense_windows=[{"start_s": 20.0, "end_s": 22.0, "interval_s": 0.25}])
        self.assertEqual([float(second) for second in range(3, 20)] + [float(second) for second in range(22, 58)],
                         [at for at, kind in zip(plan["_timestamps"], plan["_kinds"]) if kind == "body"])
        self.assertEqual((0, False), (plan["dropped_as_duplicate"]["body"], plan["body_degraded"]))

    def test_dense_window_text_and_its_limits(self) -> None:
        self.assertEqual({"start_s": 0.0, "end_s": 5.0, "interval_s": 0.25}, self.module.parse_dense_window("0:5:0.25"))
        for bad in ("0:5", "5:1:0.5", "0:5:0.1", "-1:5:0.5"):
            with self.assertRaises(ValueError):
                self.module.parse_dense_window(bad)


class OverviewPlanTest(unittest.TestCase):
    """The overview plan (acv_timing.py): a video up to 50s keeps today's frames; a longer one gets every second in
    low-resolution sheets and, in place of the body grid, a bounded set of frames where the picture or text changes."""

    def setUp(self) -> None:
        self.module = load()
        self.timing = self.module.acv_timing

    def units(self, duration, every=7):
        """A change every `every` seconds, alternating picture and text, noise below the threshold elsewhere."""
        layout = self.timing.overview_layout(duration)
        return [(0, 0)] + [((300 if index % (2 * every) == 0 else 20), (150 if index % every == 0 else 30))
                           for index in range(1, layout["tiles"])]

    def plan(self, duration, units=None, cuts=(), budget=120):
        layout = self.timing.overview_layout(duration)
        return self.module.plan_frames(duration, 3.0, 1.0, 2, budget, cuts=list(cuts),
                                       dense_windows=self.module.select_method.with_default_window([]),
                                       overview_units=units, overview_stride_s=layout["stride_s"])

    def test_thirty_seconds_is_unchanged(self) -> None:
        self.assertEqual(self.plan(30.0), self.plan(30.0, self.units(30.0)))

    def test_layouts_cover_every_second_within_sixteen_sheets(self) -> None:
        for duration, layout in ((120.0, (6, 5, 1, 4)), (600.0, (8, 7, 1, 11)), (1800.0, (12, 10, 1, 15)),
                                 (3600.4, (12, 10, 2, 15))):
            got = self.timing.overview_layout(duration)
            self.assertEqual(layout, (got["columns"], got["rows"], got["stride_s"], got["sheets"]), duration)
            self.assertGreaterEqual(got["tiles"] * got["stride_s"], round(duration))

    def test_two_ten_and_thirty_minutes_keep_a_bounded_set_of_change_frames(self) -> None:
        for duration in (120.0, 600.0, 1800.0):
            cuts = [float(second) - 0.4 for second in range(20, int(duration), 45)]
            plan = self.plan(duration, self.units(duration), cuts)
            kinds = plan["_kinds"]
            self.assertLessEqual(len(kinds), 120, duration)
            self.assertNotIn("body", kinds)
            self.assertTrue(plan["overview"])
            self.assertFalse(plan["body_degraded"])
            self.assertGreater(plan["change_frames"], 0, duration)
            changes = [at for at, kind in zip(plan["_timestamps"], kinds) if kind == "change"]
            others = [at for at, kind in zip(plan["_timestamps"], kinds) if kind not in ("change", "anchor")]
            for at in changes:
                self.assertEqual(at, int(at))
                self.assertTrue(3 <= at < duration - 2)
                self.assertTrue(all(abs(at - other) >= 1 for other in others), at)
            reasons = {reason["reason"] for reason in plan["_reasons"] if reason}
            self.assertLessEqual(reasons, {"picture_change", "text_change"})
            # Spread over the video, not bunched at its start.
            self.assertGreater(max(changes), duration / 2, duration)

    def test_a_cut_heavy_ten_minutes_keeps_the_opening_at_one_frame_a_second(self) -> None:
        """The opening before the cuts: 119 cuts on a 10-minute video no longer thin the first 50s past one frame a
        second; the shot starts take what is left after it."""
        cuts = [second * 5 - 0.4 for second in range(1, 120)]
        plan = self.plan(600.0, self.units(600.0, every=5), cuts)
        kinds, times = plan["_kinds"], plan["_timestamps"]
        self.assertEqual(120, len(kinds))
        self.assertEqual((6, 4, 47, 63), tuple(kinds.count(kind) for kind in ("hook", "closing", "dense_window",
                                                                             "shot_start")))
        self.assertEqual(1.0, plan["dense_windows"][0]["interval_s"])
        opening = sorted(at for at in times if at < 50)
        self.assertLessEqual(max(later - earlier for earlier, later in zip(opening, opening[1:])), 1.0)
        self.assertEqual(56, plan["dropped_for_budget"]["shot_start"])

    def test_a_static_video_spends_frames_only_on_anchors_in_long_gaps(self) -> None:
        quiet = [(0, 0)] * self.timing.overview_layout(300.0)["tiles"]
        plan = self.plan(300.0, quiet)
        self.assertEqual(0, plan["change_frames"])
        times = plan["_timestamps"]
        self.assertLessEqual(max(later - earlier for earlier, later in zip(times, times[1:])), 10.0)
        self.assertLess(len(times), 120)

    def test_the_change_score_reads_the_picture_and_the_text_bands(self) -> None:
        size = self.timing.LUMA_GRID_PX
        flat = bytes([60]) * (size * size)
        brighter = bytes([75]) * (size * size)
        caption = bytearray(brighter)
        for x in range(4, 60, 2):
            caption[(size - 6) * size + x] = 230
        units = self.timing.change_units(flat + flat + brighter + bytes(caption))
        self.assertEqual([(0, 0), (0, 0), (150, 0)], units[:3])
        self.assertLess(units[3][0], 100)
        self.assertGreaterEqual(units[3][1], 100)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe not installed")
class EndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dir = Path(tempfile.mkdtemp())
        cls.media = cls.dir / "a draft -- v2.mp4"  # Spaces and a leading dash are ordinary filename characters
        subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=duration=4:size=160x120:rate=10",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.media)],
            check=True, capture_output=True, timeout=300)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_signals_only_adds_the_measurement_to_the_frames_already_written(self) -> None:
        media = self.dir / "two shots.mp4"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "color=c=red:size=160x120:duration=3:rate=10",
             "-f", "lavfi", "-i", "testsrc=size=160x120:duration=3:rate=10",
             "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
             "-f", "lavfi", "-i", "sine=frequency=500:duration=2",
             "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a][4:a]concat=n=3:v=0:a=1[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             str(media)],
            check=True, capture_output=True, timeout=300)
        artifact = self.dir / "separate.json"
        subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(media),
             "--out-dir", str(self.dir / "separate"), "--artifact", str(artifact)],
            check=True, capture_output=True, timeout=600)
        frames_before = json.loads(artifact.read_text(encoding="utf-8"))["frames"]

        for _ in range(2):  # measuring twice replaces the measurement, it does not stack it
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--media", str(media), "--artifact", str(artifact),
                 "--signals-only"],
                capture_output=True, text=True, timeout=600)
            self.assertEqual(0, result.returncode, result.stderr)
        document = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(frames_before, document["frames"], "measuring must not touch the frames")
        signals = document["media"]["signals"]
        self.assertEqual(["shots", "silence", "freeze"], signals["measured"])
        self.assertEqual(2, signals["shots"]["count"])
        self.assertAlmostEqual(3.0, signals["shots"]["cuts_at_s"][0], delta=0.2)
        self.assertAlmostEqual(2.0, signals["silence"]["spans"][0]["start_s"], delta=0.2)
        operations = [step["operation"] for step in document["steps"]]
        self.assertEqual(1, operations.count("measure_shots_and_freeze"))
        self.assertEqual(1, operations.count("measure_silence"))
        summary = json.loads(result.stdout)
        self.assertEqual(frames_before["status"], summary["frames_status"])
        self.assertEqual(2, summary["signals"]["shots"])

    def test_signals_only_refuses_an_artifact_written_for_another_file(self) -> None:
        artifact = self.dir / "other.json"
        subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(self.media),
             "--out-dir", str(self.dir / "other"), "--artifact", str(artifact)],
            check=True, capture_output=True, timeout=600)
        before = artifact.read_bytes()
        other = self.dir / "another cut.mp4"
        shutil.copyfile(self.media, other)
        with other.open("ab") as handle:
            handle.write(b"\0")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(other), "--artifact", str(artifact),
             "--signals-only"],
            capture_output=True, text=True, timeout=600)
        self.assertEqual(2, result.returncode)
        self.assertIn("different file", result.stderr)
        self.assertEqual(before, artifact.read_bytes())

    def test_shot_starts_dense_windows_and_contact_sheets_on_a_cut_video(self) -> None:
        media = self.dir / "three shots.mp4"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=160x120:duration=4:rate=10",
             "-f", "lavfi", "-i", "color=c=red:size=160x120:duration=3:rate=10",
             "-f", "lavfi", "-i", "smptebars=size=160x120:duration=5:rate=10",
             "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
             "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(media)],
            check=True, capture_output=True, timeout=300)
        run = self.dir / "cuts"
        (run / "analysis").mkdir(parents=True)
        # The method cards' frame plan beside the artifact is read when no --dense-window is given.
        (run / "analysis" / "method.json").write_text(json.dumps({"frames": {
            "include_shot_starts": True, "dense_windows": [{"start_s": 0, "end_s": 2, "interval_s": 0.25}]}}))
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(media), "--out-dir", str(run / "analysis" / "frames"),
             "--artifact", str(run / "analysis" / "local-media.json")],
            capture_output=True, text=True, timeout=600)
        self.assertEqual(0, result.returncode, result.stderr)
        document = json.loads((run / "analysis" / "local-media.json").read_text(encoding="utf-8"))
        items = document["frames"]["items"]
        shots = [item["t_seconds"] for item in items if item["source"] == "shot_start"]
        self.assertEqual(2, len(shots), items)
        self.assertAlmostEqual(4.05, shots[0], delta=0.15)
        self.assertAlmostEqual(7.05, shots[1], delta=0.15)
        dense = [item["t_seconds"] for item in items if item["source"] == "dense_window"]
        self.assertEqual([0.25, 0.75, 1.25, 1.75], [at for at in dense if at < 2], "the card's window, laid first")
        # The default window: every 0.5s point of the video has a frame on it, or a cut frame within 0.25s.
        times = [item["t_seconds"] for item in items]
        for point in (index * 0.5 for index in range(24)):
            self.assertTrue(any(abs(at - point) < 0.25 for at in times), point)
        self.assertEqual([(0.0, 2.0), (0.0, 12.0)], [(window["start_s"], round(window["end_s"]))
                                                     for window in document["frames"]["sampling_plan"]["dense_windows"]])
        self.assertEqual(sorted(item["t_seconds"] for item in items), [item["t_seconds"] for item in items])
        plan = document["frames"]["sampling_plan"]
        self.assertEqual((True, "detected", 2), (plan["include_shot_starts"], plan["shot_detection"]["status"],
                                                 plan["shot_start_frames"]))
        # The cut list itself is kept, at full frame rate, for the audio measurement to line up with onsets.
        cuts = plan["shot_detection"]["cuts_at_s"]
        self.assertEqual(plan["shot_detection"]["cuts"], len(cuts))
        self.assertEqual(sorted(cuts), cuts)
        self.assertAlmostEqual(4.0, cuts[0], delta=0.1)
        self.assertAlmostEqual(7.0, cuts[1], delta=0.1)
        sheets = document["frames"]["contact_sheets"]
        # Two by two, in time order, each tile the frame's own size (160x120 here, under the 640px cap).
        self.assertEqual(-(-len(items) // 4), len(sheets))
        tiles = [tile for sheet in sheets for tile in sheet["tiles"]]
        self.assertEqual([item["frame_id"] for item in items], [tile["frame_id"] for tile in tiles])
        self.assertEqual([item["t_seconds"] for item in items], [tile["t_seconds"] for tile in tiles])
        self.assertEqual([(0, 0), (0, 1), (1, 0), (1, 1)], [(tile["row"], tile["col"]) for tile in sheets[0]["tiles"]])
        self.assertEqual((2, 2), (sheets[0]["columns"], sheets[0]["rows"]))
        for sheet in sheets:
            self.assertTrue((run / "analysis" / sheet["path"]).is_file())
            self.assertRegex(Path(sheet["path"]).name, r"^sheet-\d{2}\.jpg$")
            self.assertEqual((sheet["from_s"], sheet["to_s"]), (sheet["tiles"][0]["t_seconds"], sheet["tiles"][-1]["t_seconds"]))
        size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                               str(run / "analysis" / sheets[0]["path"])], capture_output=True, text=True, timeout=60)
        self.assertEqual("320,240", size.stdout.strip())
        summary = json.loads(result.stdout)
        self.assertEqual(len(sheets), len(summary["contact_sheets"]))
        self.assertEqual(2, summary["frame_sources"]["shot_start"])
        self.assertIn("detect_shot_starts", [step["operation"] for step in document["steps"]])

        # --dense-window replaces the method's windows (the default one still follows), and --no-shot-starts turns
        # the cut frames off; the whole video sits inside the default window, so no body point is left.
        plain = subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(media), "--out-dir", str(run / "plain"),
             "--artifact", str(run / "analysis" / "plain.json"), "--no-shot-starts", "--dense-window", "8:9:0.25",
             "--no-contact-sheets"],
            capture_output=True, text=True, timeout=600)
        self.assertEqual(0, plain.returncode, plain.stderr)
        again = json.loads((run / "analysis" / "plain.json").read_text(encoding="utf-8"))
        self.assertEqual({"hook", "closing", "dense_window"}, {item["source"] for item in again["frames"]["items"]})
        self.assertEqual([], again["frames"]["contact_sheets"])
        self.assertEqual([8.0, 0.0], [window["start_s"] for window in again["frames"]["sampling_plan"]["dense_windows"]])

    def test_a_long_file_gets_the_overview_and_change_frames(self) -> None:
        media = self.dir / "long.mp4"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "color=c=gray:size=96x160:duration=55:rate=5",
             "-f", "lavfi", "-i", "color=c=navy:size=96x160:duration=10:rate=5",
             "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
             "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(media)],
            check=True, capture_output=True, timeout=300)
        run = self.dir / "long"
        (run / "analysis").mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--media", str(media), "--out-dir", str(run / "analysis" / "frames"),
             "--artifact", str(run / "analysis" / "local-media.json"), "--no-contact-sheets", "--no-shot-starts",
             "--deadline-s", "120"],
            capture_output=True, text=True, timeout=600)
        self.assertEqual(0, result.returncode, result.stderr)
        document = json.loads((run / "analysis" / "local-media.json").read_text(encoding="utf-8"))
        overview = document["frames"]["overview"]
        self.assertEqual(("available", 1, 6, 5, 65), (overview["status"], overview["stride_s"], overview["columns"],
                                                      overview["rows"], overview["seconds"]))
        self.assertEqual([(0, 29, 30), (30, 59, 30), (60, 64, 5)],
                         [(sheet["from_s"], sheet["to_s"], sheet["tiles"]) for sheet in overview["sheets"]])
        for sheet in overview["sheets"]:
            self.assertTrue((run / "analysis" / sheet["path"]).is_file())
        self.assertFalse((run / "analysis" / "frames" / ".overview-luma.gray").exists())
        changes = [item for item in document["frames"]["items"] if item["source"] == "change"]
        # The cut at 55s is past the default window (the first 50s): with no cut frames asked for, it is the one
        # change, at a whole second, of the picture.
        self.assertEqual([(55.0, "picture_change")], [(item["t_seconds"], item["reason"]) for item in changes])
        self.assertNotIn("body", {item["source"] for item in document["frames"]["items"]})
        summary = json.loads(result.stdout)
        self.assertEqual(3, len(summary["overview"]["sheets"]))
        self.assertIn("overview", [step["operation"] for step in document["steps"]])

    def test_ffmpeg_progress_reports_how_far_a_pass_read(self) -> None:
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-progress", "pipe:1", "-an",
             "-i", str(self.media), "-map", "0:v:0", "-f", "null", "-"],
            check=True, capture_output=True, text=True, timeout=120)
        self.assertAlmostEqual(4.0, load().progress_seconds(result.stdout), delta=0.25)



if __name__ == "__main__":
    unittest.main()
