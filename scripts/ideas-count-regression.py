#!/usr/bin/env python3
"""核验显式数量从请求到报告及日历交接，不把合成内容当效果验收。"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/develop-content-ideas"
CALENDAR = ROOT / "skills/plan-content-calendar"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL / "scripts"))
import validate_ideas as validator

FIXTURE = json.loads((ROOT / "scripts/fixtures/ideas-continuation.json").read_text())


class IdeaCounts(unittest.TestCase):
    def setUp(self):
        """每个测试独立目录，不重置已有生成预算。"""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def write(self, root, name, value):
        """保持JSON落盘格式稳定，便于跨包核对真实摘要。"""
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return path

    def stage(self, root, stage, *flags):
        """执行正式prep/core入口并读取其结构化状态。"""
        result = subprocess.run([sys.executable, "-B", str(SKILL / "scripts/run_ideas_stages.py"),
            stage, "--run-dir", str(root), *map(str, flags)], capture_output=True, text=True)
        self.assertTrue(result.stdout, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def intent(self, count):
        """在既有有效夹具上只替换数量和明确主题。"""
        intent = copy.deepcopy(FIXTURE["intent"])
        intent["idea_count"] = count
        intent["user_brief"]["text"] = f"Give me {count} AI sales workflow ideas for Instagram."
        intent["generation_basis"] = {"direct_topic": "AI sales workflow", "required_sources": [],
                                      "allow_brief_fallback": False}
        return intent

    def output(self, count):
        """合成数量合同夹具，创意质量由独立模型回归评分。"""
        output = copy.deepcopy(FIXTURE["idea_set"])
        output["ideas"] = []
        for rank in range(1, count + 1):
            idea = copy.deepcopy(FIXTURE["idea"])
            idea.update(idea_id=f"idea-{rank:03d}", rank=rank,
                        working_title=f"Workflow decision {rank:03d}")
            output["ideas"].append(idea)
        return output

    def prepare(self, root, count):
        """返回真实构建的请求，要求合法数量进入生成阶段。"""
        path = self.write(root, "intent.json", self.intent(count))
        code, prep = self.stage(root, "prep", "--intent", path)
        self.assertEqual((0, "ok", "ready_for_generation"),
                         (code, prep["status"], prep.get("decision", {}).get("status")), prep)
        return json.loads((root / "request.json").read_text())

    def test_supported_counts_reach_core_and_every_report_item(self):
        """旧小批量和新15/20批量均完整经过校验、渲染。"""
        for count in (3, 10, 15, 20):
            with self.subTest(count=count):
                root = self.root / str(count)
                request = self.prepare(root, count)
                self.assertEqual(count, request["idea_count"])
                output = self.output(count)
                self.write(root, "idea_set.json", output)
                code, core = self.stage(root, "core")
                self.assertEqual((0, "ok", 1), (code, core["status"], core["generation_attempts"]), core)
                report = (root / "RESULT.md").read_text()
                for idea in output["ideas"]:
                    self.assertIn(idea["working_title"], report)

    def test_out_of_range_counts_and_missing_count_do_not_generate(self):
        """保留短名单下限和显式数量必填要求，不悄悄补默认值。"""
        for count in (2, 21, None):
            with self.subTest(count=count):
                root = self.root / str(count)
                intent = self.intent(count)
                if count is None:
                    del intent["idea_count"]
                path = self.write(root, "intent.json", intent)
                _, prep = self.stage(root, "prep", "--intent", path)
                self.assertEqual("needs_correction", prep["status"], prep)
                self.assertIn("idea_count", json.dumps(prep))
                self.assertFalse((root / "RESULT.md").exists())

    def test_requested_twenty_cannot_be_truncated_to_ten(self):
        """宽上限不放松请求与结果的数量相等约束。"""
        request = self.prepare(self.root, 20)
        errors = validator.validate_idea_set(self.output(10), request, self.root / "idea_set.json")
        self.assertTrue(any("ideas count must equal" in e for e in errors), errors)

    def test_missing_required_trend_still_blocks_large_batch(self):
        """数量扩大不能绕过显式研究输入的缺失门槛。"""
        intent = self.intent(20)
        intent["generation_basis"]["required_sources"] = ["trend"]
        path = self.write(self.root, "intent.json", intent)
        code, prep = self.stage(self.root, "prep", "--intent", path)
        self.assertEqual(0, code)
        self.assertEqual("blocked_missing_required_source", prep["decision"]["status"], prep)
        self.assertEqual(["trend"], prep["decision"]["missing_required_sources"])

    def test_rework_count_and_hook_constraints_are_unchanged(self):
        """单条改写仍仅1个选题，Hook数量仍3至5。"""
        request = self.prepare(self.root, 3)
        request.update(task_intent="rework_content", idea_count=1, hook_option_count=3)
        errors = validator.validate_request(request, self.root / "request.json")
        self.assertFalse(any("idea_count" in e or "Hook options" in e for e in errors), errors)
        self.assertTrue(any("VideoAnalysis" in e for e in errors), errors)
        request.update(idea_count=20, hook_option_count=2)
        errors = validator.validate_request(request, self.root / "request.json")
        self.assertTrue(any("rework_content requires idea_count=1" in e for e in errors), errors)
        self.assertTrue(any("3..5 Hook options" in e for e in errors), errors)

    def test_capacity_budget_is_not_relaxed_for_twenty(self):
        """20条容量计划仍需全部估时落在已给预算内。"""
        request = self.prepare(self.root, 20)
        request["task_intent"] = "capacity_plan"
        request["production_constraints"]["total_time_minutes"] = 600
        output = self.output(20)
        output["task_intent"] = "capacity_plan"
        output["evidence_gap_translations"].append({"source_text": "capacity_plan", "report_text": "capacity plan"})
        self.assertEqual([], validator.validate_request(request, self.root / "request.json"))
        self.assertEqual([], validator.validate_idea_set(output, request, self.root / "idea_set.json"))
        request["production_constraints"]["total_time_minutes"] = 599
        errors = validator.validate_idea_set(output, request, self.root / "idea_set.json")
        self.assertTrue(any("exceed budget" in e for e in errors), errors)

    def test_chat_helper_preserves_twenty_through_prep(self):
        """续聊helper也支持20，保留精确前文引用后再走正常prep。"""
        messages = self.write(self.root, "messages.json", [{"role": "assistant", "text": "A workflow stops before promising a price."}])
        brief = self.root / "query.txt"
        brief.write_text("Give me 20 more in that style.")
        result = subprocess.run([sys.executable, "-B", str(SKILL / "scripts/prepare_conversation_inputs.py"),
            "--messages", str(messages), "--reference-index", "0", "--reference-quote", "A workflow stops before promising a price.",
            "--brief-file", str(brief), "--idea-count", "20", "--platform", "instagram", "--language", "en",
            "--continuation-quote", "20 more in that style", "--run-dir", str(self.root)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        _, prep = self.stage(self.root, "prep", "--intent", self.root / "intent.json",
                             "--conversation-context", self.root / "conversation-source.json")
        self.assertEqual("ready_for_generation", prep["decision"]["status"], prep)
        self.assertEqual(20, json.loads((self.root / "request.json").read_text())["idea_count"])

    def test_calendar_accepts_large_set_only_as_unselected_backlog(self):
        """日历接收真实生成的20条候选，但不把候选擅自排成已选内容。"""
        self.prepare(self.root, 20)
        ideas = self.output(20)
        idea_path = self.write(self.root, "idea_set.json", ideas)
        self.assertEqual("ok", self.stage(self.root, "core")[1]["status"])
        request = {
            "schema_version": "content-calendar-request.v1", "request_id": "calendar-count",
            "created_at": "2026-11-08T00:00:00Z", "language": "en", "intent": "four_week_plan",
            "single_slot_decision": None,
            "planning_window": {"start_date": "2026-11-09", "weeks": 4, "timezone": "UTC", "timezone_source": "creator_confirmed"},
            "items": [], "candidate_idea_set_refs": [{"path": idea_path.name, "artifact_id": ideas["idea_set_id"],
                "schema_version": ideas["schema_version"], "sha256": hashlib.sha256(idea_path.read_bytes()).hexdigest()}],
            "cadence_rules": [{"account_ref": "fixture-account", "platform": "instagram",
                "publish_format": "REELS", "production_format": "short_form", "posts_per_week": 2,
                "preferred_weekdays": [1, 4], "preferred_local_times": ["18:00"]}],
            "capacity": {"status": "unavailable", "weekly_minutes": None, "week_overrides": [], "blackout_dates": []},
            "constraints": {"max_posts_per_day": 1, "min_publish_gap_hours": 24, "production_lead_hours": 0},
            "reminder_preferences": {"pre_publish_minutes": [], "post_publish_attention_minutes": []},
        }
        request_path = self.write(self.root, "calendar-request.json", request)
        for script, args in [
            ("validate_content_calendar.py", ["request", str(request_path), "--run-root", str(self.root)]),
            ("build_content_calendar.py", [str(request_path), "--run-root", str(self.root), "--output", str(self.root / "calendar.json")]),
        ]:
            result = subprocess.run([sys.executable, "-B", str(CALENDAR / "scripts" / script), *args], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        calendar = json.loads((self.root / "calendar.json").read_text())
        self.assertEqual([], calendar["slots"])
        self.assertTrue(any(x["reason"] == "candidate_requires_selection" for x in calendar["unscheduled"]), calendar)


if __name__ == "__main__":
    unittest.main()
