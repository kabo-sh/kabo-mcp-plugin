#!/usr/bin/env python3
"""验证实际命令交付中的预测证据，不用模型输出替代脚本检查。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/review-creator-account/scripts/estimate_growth.py"


class GrowthHandoff(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.scope = dict(platform="youtube", account="creator", metric="subscribers", semantics="cumulative_stock")

    def row(self, date, value, source):
        return dict(observed_at=date, value=value, source=source, scope=self.scope)

    def run_estimate(self, name, data, question=""):
        source = self.root / f"{name}-input.json"
        source.write_text(json.dumps(data))
        prompt = self.root / f"{name}-question.txt"
        prompt.write_text(question)
        output = self.root / f"{name}.json"
        run = subprocess.run([sys.executable, "-B", str(SCRIPT), str(source), "--question-file", str(prompt), "--output", str(output)], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(output.read_text()), output.with_suffix(".md").read_text(), run.stdout

    def test_observed_window_and_every_source_survive_delivery(self):
        data = dict(schema_version="growth-input.v1", mode="observed_pace", scope=self.scope, horizon_days=14,
                    observations=[self.row("2026-10-08T00:00:00Z", 148, "owner export row 3"),
                                  self.row("2026-10-01T00:00:00Z", 120, "owner export row 1"),
                                  self.row("2026-10-04T00:00:00Z", 125, "owner export row 2")])
        result, report, stdout = self.run_estimate("observed", data)
        self.assertEqual(result["estimate"]["value"], 204)
        for row in data["observations"]:
            self.assertIn(row["observed_at"], report)
            self.assertIn(row["source"], report)
        self.assertIn("(7 days)", report)
        self.assertIn("14 days after this observation, not after today", report)
        self.assertIn(report.strip(), stdout)

    def test_single_post_baseline_accepts_a_bound_user_rate(self):
        self.scope.update(account="creator/post-1", metric="views")
        data = dict(schema_version="growth-input.v1", mode="assumed_pace", scope=self.scope, horizon_days=14,
                    observations=[self.row("2026-11-01T00:00:00Z", 1000, "post export row 1")],
                    assumption=dict(amount=100, period="day", origin="user", quote="100 per day"))
        result, report, _ = self.run_estimate("assumed", data, "Assume 100 per day for this post.")
        self.assertEqual(result["estimate"]["value"], 2400)
        self.assertIn("2026-11-01T00:00:00Z", report)
        self.assertIn("post export row 1", report)
        self.assertIn("User-supplied rate quote: 100 per day", report)
        self.assertIn("not a calibrated forecast or probability", report)

    def test_unbound_rate_remains_missing_input(self):
        data = dict(schema_version="growth-input.v1", mode="assumed_pace", scope=self.scope, horizon_days=14,
                    observations=[self.row("2026-11-01T00:00:00Z", 100, "owner export")],
                    assumption=dict(amount=20, period="week", origin="user", quote="20 subscribers per week"))
        result, report, _ = self.run_estimate("unbound", data, "Give me a forecast without assuming a growth rate.")
        self.assertEqual(result["status"], "needs_input")
        self.assertIsNone(result["estimate"])
        self.assertIn("No numeric estimate or probability", report)

    def test_extra_content_metrics_keep_separate_handoffs(self):
        outputs = {}
        for metric, values in [("views", [1000, 2000, 3000]), ("likes", [10, 20, 30])]:
            scope = dict(platform="youtube", account="creator", metric=metric, semantics="per_content_cumulative")
            rows = [dict(content_id=f"post-{n}", published_at="2026-10-01T00:00:00Z", observed_at="2026-10-11T00:00:00Z", format="short", value=v, source=f"owner {metric} row {n}", scope=scope) for n, v in enumerate(values)]
            data = dict(schema_version="growth-input.v1", mode="content_scenario", scope=scope, horizon_days=30,
                        samples=rows, cohort=dict(format="short", age_min_days=10, age_max_days=10),
                        plan=dict(posts=4, origin="user", quote="4 videos"))
            outputs[metric] = self.run_estimate(metric, data, "4 videos")
        self.assertEqual(outputs["views"][0]["estimate"]["value"], 8000)
        self.assertEqual(outputs["likes"][0]["estimate"]["value"], 80)
        self.assertEqual(json.loads((self.root / "views.json").read_text())["scope"]["metric"], "views")
        self.assertEqual(json.loads((self.root / "likes.json").read_text())["scope"]["metric"], "likes")
        self.assertIn("/ views", outputs["views"][1])
        self.assertIn("/ likes", outputs["likes"][1])


if __name__ == "__main__":
    unittest.main()
