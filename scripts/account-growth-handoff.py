#!/usr/bin/env python3
"""验证实际命令交付中的预测证据，不用模型输出替代脚本检查。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/review-creator-account/scripts/estimate_growth.py"
COMPOSER = SCRIPT.with_name("compose_forecast_reply.py")


class GrowthHandoff(unittest.TestCase):
    def setUp(self):
        """创建隔离目录和默认指标范围，测试结束自动清理。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.scope = dict(platform="youtube", account="creator", metric="subscribers", semantics="cumulative_stock")

    def row(self, date, value, source):
        """构造带来源和范围的已知观测记录。"""
        return dict(observed_at=date, value=value, source=source, scope=self.scope)

    def run_estimate(self, name, data, question=""):
        """执行真实计算命令并读取其结果与交付文本。"""
        source = self.root / f"{name}-input.json"
        source.write_text(json.dumps(data))
        prompt = self.root / f"{name}-question.txt"
        prompt.write_text(question)
        output = self.root / f"{name}.json"
        run = subprocess.run([sys.executable, "-B", str(SCRIPT), str(source), "--question-file", str(prompt), "--output", str(output)], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(output.read_text()), output.with_suffix(".md").read_text(), run.stdout

    def test_observed_window_and_every_source_survive_delivery(self):
        """验证交付保留真实观测窗口、日期和每条来源。"""
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
        """验证单条视频基线与用户明确速率能够计算。"""
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
        """验证并非用户提供的增长率不能进入计算。"""
        data = dict(schema_version="growth-input.v1", mode="assumed_pace", scope=self.scope, horizon_days=14,
                    observations=[self.row("2026-11-01T00:00:00Z", 100, "owner export")],
                    assumption=dict(amount=20, period="week", origin="user", quote="20 subscribers per week"))
        result, report, _ = self.run_estimate("unbound", data, "Give me a forecast without assuming a growth rate.")
        self.assertEqual(result["status"], "needs_input")
        self.assertIsNone(result["estimate"])
        self.assertIn("No numeric estimate or probability", report)

    def test_undated_snapshot_is_not_reconstructed_for_a_forecast(self):
        """验证缺测量日期时不补造观测用于计算。"""
        self.scope.update(account="creator/named-post", metric="views")
        data = dict(schema_version="growth-input.v1", mode="observed_pace", scope=self.scope,
                    horizon_days=365, observations=[])
        result, report, stdout = self.run_estimate("missing", data)
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual(result["observations"], [])
        self.assertIsNone(result["estimate"])
        self.assertIn("creator/named-post / views", report)
        self.assertIn("Two dated observations", report)
        self.assertIn("No numeric estimate or probability", report)
        self.assertIn(report.strip(), stdout)

    def test_extra_content_metrics_keep_separate_handoffs(self):
        """验证额外指标独立保存，不覆盖首个计算结果。"""
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

    def test_valid_rate_without_baseline_asks_only_for_baseline(self):
        """验证已有有效增长率时仅索要缺失基线。"""
        data = dict(schema_version="growth-input.v1", mode="assumed_pace", scope=self.scope,
                    horizon_days=14, observations=[],
                    assumption=dict(amount=20, period="week", origin="user", quote="20 subscribers per week"))
        result, report, _ = self.run_estimate("missing-baseline", data, "Assume 20 subscribers per week.")
        self.assertEqual(result["required_inputs"], ["A dated baseline for the requested cumulative metric."])
        self.assertEqual(result["status"], "needs_input")
        self.assertNotIn("Two dated observations", report)

    def test_content_aliases_preserve_sample_evidence_and_missingness(self):
        """验证格式别名不丢失样本，交付保留来源与缺失统计。"""
        scope = dict(platform="instagram", account="creator", metric="likes", semantics="per_content_cumulative")
        rows = [dict(content_id=f"post-{n}", published_at="2026-10-01T00:00:00Z",
                     observed_at="2026-10-11T00:00:00Z", format=fmt, value=value,
                     source=f"owner export row {n}", scope=scope)
                for n, (fmt, value) in enumerate([("instagram_feed", 10), ("feed", 20),
                                                  ("image", 30), ("feed", None), ("reel", 999)])]
        data = dict(schema_version="growth-input.v1", mode="content_scenario", scope=scope,
                    horizon_days=30, samples=rows, cohort=dict(format="instagram_feed", age_min_days=10, age_max_days=10),
                    plan=dict(posts=4, origin="user", quote="4 videos"))
        result, report, _ = self.run_estimate("aliases", data, "4 videos")
        self.assertEqual(result["estimate"]["value"], 80)
        self.assertEqual(result["coverage"], dict(available=3, missing=1, outside_cohort=1))
        self.assertIn("Cohort: feed", report)
        self.assertIn("3 available, 1 missing values, 1 outside", report)
        for row in rows[:3]:
            self.assertIn(row["source"], report)
            self.assertIn(row["observed_at"], report)
            self.assertIn(row["published_at"], report)
        self.assertNotIn("999", report)

    def test_snapshot_cadence_uses_equivalent_formats(self):
        """验证同义格式在快照发布频率计算中一致归类。"""
        scope = dict(platform="instagram", account="creator", metric="likes", semantics="per_content_cumulative")
        data = dict(schema_version="growth-input.v1", mode="content_scenario", scope=scope,
                    horizon_days=14, cohort=dict(format="feed", age_min_days=0, age_max_days=30),
                    plan=dict(origin="observed_cadence"))
        snapshot = dict(schema_version="public-content-snapshot.v1", platform="instagram",
                        creators=[dict(creator_id="c", handle="creator")], observed_at="2026-10-15T00:00:00Z",
                        items=[dict(content_id=f"post-{n}", creator_id="c", published_at=date,
                                    format=fmt, metrics=dict(likes=dict(status="available", value=value)))
                               for n, (date, fmt, value) in enumerate([("2026-10-01T00:00:00Z", "instagram_feed", 10),
                                                                       ("2026-10-08T00:00:00Z", "image", 30)])])
        source, saved, output = [self.root / name for name in ["input.json", "snapshot.json", "growth.json"]]
        source.write_text(json.dumps(data)); saved.write_text(json.dumps(snapshot))
        run = subprocess.run([sys.executable, "-B", str(SCRIPT), str(source), "--snapshot", str(saved),
                              "--output", str(output)], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(output.read_text())
        self.assertEqual(result["estimate"]["value"], 40)
        self.assertEqual(result["basis"]["sample_size"], 2)
        self.assertEqual(result["basis"]["input_binding"]["captured_posts"], 2)
        self.assertIn("snapshot.json#items/post-1", output.with_suffix(".md").read_text())

    def compose_reply(self, inputs, output_name="reply.md", flags=()):
        """执行完整回复组合器，不以模拟结果替代实际计算。"""
        scope_file = self.root / "scope.json"
        scope_file.write_text(json.dumps(dict(platform=self.scope["platform"], target=self.scope["account"],
                                              request_quote="Forecast the selected account.", reference="The account selected by the user.")))
        command = [sys.executable, "-B", str(COMPOSER), "--scope-file", str(scope_file), "--output", str(self.root / output_name)]
        for n, data in enumerate(inputs):
            path = self.root / f"compose-{n}.json"
            path.write_text(json.dumps(data))
            command += ["--input", str(path)]
        return subprocess.run([*command, *flags], text=True, capture_output=True)

    def test_scope_errors_name_all_problems_and_allow_one_targeted_repair(self):
        """真实失败形态：范围文件误放时长；诊断指明多余字段而不放宽校验。"""
        source = self.root / "scope.json"
        output = self.root / "reply.md"
        scope = dict(platform="youtube", target="creator/post-1", request_quote="continue this post",
                     reference="Selected post", horizon_days=365)
        command = [sys.executable, "-B", str(COMPOSER), "--scope-file", str(source),
                   "--missing-metric", "views", "--horizon-days", "365", "--output", str(output)]
        for bad, message in [(scope, "unexpected fields: horizon_days"),
                             ({**scope, "reference": []}, "must be nonempty strings: reference"),
                             ({key: value for key, value in scope.items() if key != "request_quote"},
                              "missing fields: request_quote")]:
            source.write_text(json.dumps(bad))
            run = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(0, run.returncode)
            self.assertIn(message, run.stderr)
            self.assertIn("not in the scope file", run.stderr)
            self.assertFalse(output.exists())
        del scope["horizon_days"]
        source.write_text(json.dumps(scope))
        run = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertTrue(output.exists())
        result = json.loads(output.with_suffix(".json").read_text())["results"][0]
        self.assertEqual("needs_input", result["status"])
        self.assertIsNone(result["estimate"])

    def test_missing_metrics_build_valid_inputs_for_one_post(self):
        """缺数据快捷入口生成同一目标的合法合同，不需要模型填模式/schema。"""
        self.scope['account'] = 'creator/post-1'
        run = self.compose_reply([], flags=['--missing-metric', 'views', '--missing-metric', 'likes',
                                           '--horizon-days', '365', '--correct-prior'])
        self.assertEqual(0, run.returncode, run.stderr)
        results = json.loads((self.root / 'reply.json').read_text())['results']
        self.assertEqual(['views', 'likes'], [r['scope']['metric'] for r in results])
        for result in results:
            self.assertEqual(('creator/post-1', 'needs_input', 365),
                             (result['scope']['account'], result['status'], result['horizon_days']))
            self.assertEqual([], result['observations'])
            self.assertIsNone(result['estimate'])
        self.assertIn('Earlier unsupported', run.stdout)
        self.assertIn('Two dated observations', run.stdout)

    def test_missing_shortcut_preserves_independently_supported_metric(self):
        """快捷缺测量指标不得压掉已有可算指标。"""
        supported = dict(schema_version='growth-input.v1', mode='observed_pace', scope=self.scope, horizon_days=14,
                         observations=[self.row('2026-10-01T00:00:00Z', 120, 'owner row 1'),
                                       self.row('2026-10-08T00:00:00Z', 148, 'owner row 2')])
        run = self.compose_reply([supported], flags=['--missing-metric', 'views', '--horizon-days', '14'])
        self.assertEqual(0, run.returncode, run.stderr)
        results = json.loads((self.root / 'reply.json').read_text())['results']
        self.assertEqual(204, results[0]['estimate']['value'])
        self.assertEqual('needs_input', results[1]['status'])

    def test_missing_shortcut_rejects_invalid_metric_horizon_and_duplicates(self):
        """无效名称/时长/重复仍拒收，不能借缺数据绕过合同。"""
        for flags in [[], ['--missing-metric', 'sales', '--horizon-days', '30'],
                      ['--missing-metric', 'views'], ['--missing-metric', 'views', '--horizon-days', 'nan'],
                      ['--missing-metric', 'views', '--horizon-days', '0'],
                      ['--missing-metric', 'views', '--missing-metric', 'views', '--horizon-days', '30']]:
            with self.subTest(flags=flags):
                run = self.compose_reply([], flags=flags)
                self.assertNotEqual(0, run.returncode)
                self.assertFalse((self.root / 'reply.md').exists())

    def test_composed_reply_delivers_supported_and_missing_metrics_together(self):
        """验证可算指标和缺数据指标在同一回复中独立交付。"""
        supported = dict(schema_version="growth-input.v1", mode="observed_pace", scope=self.scope, horizon_days=14,
                         observations=[self.row("2026-10-01T00:00:00Z", 120, "owner row 1"),
                                       self.row("2026-10-08T00:00:00Z", 148, "owner row 2")])
        missing = dict(schema_version="growth-input.v1", mode="observed_pace",
                       scope={**self.scope, "metric": "views"}, horizon_days=14, observations=[])
        run = self.compose_reply([supported, missing])
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads((self.root / "reply.json").read_text())["results"]
        self.assertEqual(result[0]["estimate"]["value"], 204)
        self.assertEqual(result[1]["status"], "needs_input")
        report = (self.root / "reply.md").read_text()
        self.assertIn("204.00", report)
        self.assertIn("## views", report)
        self.assertIn("No numeric estimate or probability", report)
        self.assertEqual(run.stdout, "KABO_FORECAST_REPLY_BEGIN\n" + report + "KABO_FORECAST_REPLY_END\n")

    def test_composer_rejects_a_different_target_and_writes_no_report(self):
        """验证混入另一预测对象时拒绝生成报告。"""
        a = dict(schema_version="growth-input.v1", mode="observed_pace", scope=self.scope, horizon_days=30, observations=[])
        b = {**a, "scope": {**self.scope, "account": "creator/post-1"}}
        run = self.compose_reply([a, b])
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("one resolved target", run.stderr)
        self.assertFalse((self.root / "reply.md").exists())
        self.assertFalse((self.root / "reply.json").exists())

    def test_composer_does_not_overwrite_input_evidence(self):
        """验证回复输出路径不会覆盖输入证据。"""
        data = dict(schema_version="growth-input.v1", mode="observed_pace", scope=self.scope, horizon_days=30, observations=[])
        run = self.compose_reply([data], "compose-0.md")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("must not overwrite", run.stderr)
        self.assertEqual(json.loads((self.root / "compose-0.json").read_text()), data)


if __name__ == "__main__":
    unittest.main()
