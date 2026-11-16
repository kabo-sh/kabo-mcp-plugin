#!/usr/bin/env python3
"""The one-command forecast builds every calculation input itself; the model passes facts, never JSON."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/review-creator-account/scripts/forecast.py"


class ForecastEntry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def run_forecast(self, question, *args, expect=0):
        """Run the real command with the question on stdin, as the Skill tells the host to."""
        run = subprocess.run([sys.executable, "-B", str(SCRIPT), "--question-file", "-",
                              "--output", str(self.root / "FORECAST_REPLY.md"), *args],
                             input=question, text=True, capture_output=True)
        self.assertEqual(run.returncode, expect, run.stdout + run.stderr)
        return run.stdout

    def snapshot(self):
        items = [dict(creator_id="c1", content_id=f"v{day}", published_at=f"2026-10-{day:02d}T12:00:00Z",
                      format="short", metrics={"views": {"status": "available", "value": views}})
                 for day, views in ((1, 500), (5, 900), (9, 700), (13, 1100))]
        items.append(dict(creator_id="c1", content_id="long1", published_at="2026-10-03T12:00:00Z",
                          format="video", metrics={"views": {"status": "available", "value": 4000}}))
        path = self.root / "snapshot.json"
        path.write_text(json.dumps(dict(schema_version="public-content-snapshot.v1", platform="youtube",
                                        observed_at="2026-10-20T00:00:00Z",
                                        creators=[dict(handle="@creator", creator_id="c1")], items=items)))
        return path

    def test_single_new_video_without_history_asks_for_records(self):
        """The failing production shape: one new video's views and its odds, no saved history."""
        out = self.run_forecast("How many views will this reel get, and what are its chances?",
                                "--platform", "instagram", "--target", "@creator", "--metric", "views",
                                "--posts", "1", "--horizon-days", "1")
        self.assertIn("KABO_FORECAST_REPLY_BEGIN", out)
        self.assertIn("No numeric estimate or probability is available", out)
        self.assertIn("Occurrence probabilities are unavailable", out)
        inputs = json.loads((self.root / "forecast_input_views.json").read_text())
        self.assertEqual(inputs["plan"], {"origin": "request_item", "posts": 1})
        scope = json.loads((self.root / "forecast_scope.json").read_text())
        self.assertEqual(scope["target"], inputs["scope"]["account"])

    def test_single_new_video_with_snapshot_uses_the_median_item(self):
        out = self.run_forecast("How many views will my next short get?", "--platform", "youtube",
                                "--target", "@creator", "--metric", "views", "--posts", "1",
                                "--snapshot", str(self.snapshot()))
        result = json.loads((self.root / "FORECAST_REPLY.json").read_text())["results"][0]
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["cohort"]["format"], "short")
        self.assertEqual(result["estimate"]["value"], 800)
        self.assertIn("800.00", out)

    def test_every_content_metric_uses_one_format(self):
        path = self.snapshot()
        data = json.loads(path.read_text())
        data["items"][-1]["metrics"]["likes"] = {"status": "available", "value": 4000}
        path.write_text(json.dumps(data))
        self.run_forecast("Views and likes of my next short?", "--platform", "youtube", "--target", "@creator",
                          "--metric", "views", "--metric", "likes", "--posts", "1", "--snapshot", str(path))
        results = json.loads((self.root / "FORECAST_REPLY.json").read_text())["results"]
        self.assertEqual({r["cohort"]["format"] for r in results}, {"short"})

    def test_snapshot_that_is_not_an_object_is_a_reported_failure(self):
        path = self.root / "bad.json"
        path.write_text("[1, 2]")
        out = self.run_forecast("views?", "--platform", "youtube", "--target", "@creator", "--metric", "views",
                                "--snapshot", str(path), expect=2)
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["reason"], "forecast_request_invalid")

    def test_observed_cadence_is_the_default_plan(self):
        self.run_forecast("How many views next month?", "--platform", "youtube", "--target", "@creator",
                          "--metric", "views", "--snapshot", str(self.snapshot()))
        result = json.loads((self.root / "FORECAST_REPLY.json").read_text())["results"][0]
        self.assertEqual(result["status"], "computed")
        self.assertEqual(result["basis"]["plan"]["origin"], "observed_cadence")

    def test_dated_subscriber_records_and_missing_metric_together(self):
        out = self.run_forecast("I had 120 subs on Oct 1 and 148 on Oct 8. Subscribers and views in 14 days?",
                                "--platform", "youtube", "--target", "@creator", "--metric", "subscribers",
                                "--metric", "views", "--horizon-days", "14",
                                "--record", "subscribers@2026-10-01=120", "--record", "subscribers@2026-10-08=148")
        results = json.loads((self.root / "FORECAST_REPLY.json").read_text())["results"]
        self.assertEqual([r["status"] for r in results], ["computed", "needs_input"])
        self.assertEqual(results[0]["estimate"]["value"], 204)
        self.assertIn("2026-10-01T00:00:00+00:00", out)

    def test_user_rate_is_bound_from_the_exact_excerpt(self):
        self.run_forecast("I have 1000 subscribers today (2026-11-01) and gain 20 subscribers per week. In 28 days?",
                          "--platform", "youtube", "--target", "@creator", "--metric", "subscribers",
                          "--horizon-days", "28", "--record", "subscribers@2026-11-01=1000",
                          "--rate", "20 subscribers per week")
        result = json.loads((self.root / "FORECAST_REPLY.json").read_text())["results"][0]
        self.assertEqual(result["mode"], "assumed_pace")
        self.assertEqual(result["estimate"]["value"], 1080)

    def test_one_posts_own_views(self):
        self.run_forecast("This post had 1000 views on Nov 1 and 1600 on Nov 4. Views in a week?",
                          "--platform", "tiktok", "--target", "https://www.tiktok.com/@c/video/1",
                          "--target-kind", "post", "--metric", "views", "--horizon-days", "7",
                          "--record", "views@2026-11-01=1000", "--record", "views@2026-11-04=1600")
        result = json.loads((self.root / "FORECAST_REPLY.json").read_text())["results"][0]
        self.assertEqual(result["scope"]["semantics"], "cumulative_stock")
        self.assertEqual(result["estimate"]["value"], 3000)

    def test_bad_record_is_a_reported_failure_with_a_reason(self):
        out = self.run_forecast("subs?", "--platform", "youtube", "--target", "@creator", "--metric", "subscribers",
                                "--record", "subscribers=120", expect=2)
        failure = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["reason"], "forecast_request_invalid")


if __name__ == "__main__":
    unittest.main()
