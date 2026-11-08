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

    def test_previous_large_set_keeps_all_candidates_in_followup(self):
        """15/20条已验收候选可继续引用，不能在前文投影时截断。"""
        for count in (15, 20):
            with self.subTest(count=count):
                previous = self.root / f"previous-{count}"
                self.prepare(previous, count)
                output = self.output(count)
                source = self.write(previous, "idea_set.json", output)
                self.assertEqual("ok", self.stage(previous, "core")[1]["status"])
                followup = self.root / f"followup-{count}"
                intent = self.intent(3)
                intent["request_id"] = f"followup-after-{count}"
                intent["user_brief"]["text"] = "Give me three more in that style."
                intent["generation_basis"].update(direct_topic=None, continuation_quote="more in that style")
                path = self.write(followup, "intent.json", intent)
                code, prep = self.stage(followup, "prep", "--intent", path, "--previous-ideas", source)
                self.assertEqual((0, "ok", "ready_for_generation"),
                                 (code, prep["status"], prep.get("decision", {}).get("status")), prep)
                request = json.loads((followup / "request.json").read_text())
                self.assertEqual(3, request["idea_count"])
                context = request["continuation_context"]
                self.assertEqual([idea["idea_id"] for idea in output["ideas"]],
                                 [idea["idea_id"] for idea in context["ideas"]])
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), context["sha256"])
                self.assertEqual(source.read_bytes(), (followup / context["path"]).read_bytes())

    def test_schema_errors_do_not_hide_pending_assets_from_the_only_revision(self):
        """20条的格式、翻译和素材状态同轮报全，一次修订后完整交付。"""
        self.prepare(self.root, 20)
        output = self.output(20)
        output["evidence_gap_translations"] = []
        for idea in output["ideas"]:
            idea["hook_options"] = [{"option_id": "unused", "opening_line": "A second opening",
                                     "progressive_line": None, "mechanism": "contrast", "rationale": "example"}]
            idea["production_feasibility"].update(status="assessed", required_assets=["A consenting guest"],
                                                  assets_used=[], assumptions=[])
        self.write(self.root, "idea_set.json", output)
        code, first = self.stage(self.root, "core")
        self.assertEqual((0, "needs_revision", 1), (code, first["status"], first["revision_remaining"]))
        messages = "\n".join(first["errors"])
        self.assertIn("hook_options", messages)
        self.assertIn("evidence_gap_translations", messages)
        for idea in output["ideas"]:
            prefix = idea["idea_id"]
            self.assertIn(f'{prefix}: undeclared required_assets require production_feasibility.status="requires_user_confirmation"', messages)
            self.assertIn(f"{prefix}: undeclared required_assets require explicit production assumptions", messages)
            self.assertIn(f"{prefix}: undeclared required_assets require a production_missing gate", messages)
            idea["hook_options"] = []
            idea["production_feasibility"].update(status="requires_user_confirmation",
                                                  assumptions=["Confirm a consenting guest before filming."])
        self.assertFalse((self.root / "RESULT.md").exists())
        output["evidence_gap_translations"] = self.output(20)["evidence_gap_translations"]
        output["gates"]["production_missing"] = ["Confirm a consenting guest before filming."]
        output["interaction"]["next_actions"].append("answer_production_question")
        self.write(self.root, "idea_set.json", output)
        code, revised = self.stage(self.root, "core")
        self.assertEqual((0, "ok", 2), (code, revised["status"], revised["generation_attempts"]), revised)
        report = (self.root / "RESULT.md").read_text()
        for idea in output["ideas"]:
            self.assertIn(idea["working_title"], report)
        self.assertIn("Confirm a consenting guest before filming.", report)

    def test_translation_repair_targets_display_values_not_nested_statuses(self):
        """首次反馈区分顶层展示与素材状态；按缺项修订一次即可交付全部20条。"""
        self.prepare(self.root, 20)
        output = self.output(20)
        output["evidence_gap_translations"] = []
        self.write(self.root, "idea_set.json", output)
        _, first = self.stage(self.root, "core")
        message = "; ".join(first["errors"])
        self.assertIn("Add exactly these missing source_text entries", message)
        self.assertIn("top-level IdeaSet.status", message)
        self.assertIn("production_feasibility.status are not display values", message)
        output["evidence_gap_translations"] = self.output(20)["evidence_gap_translations"]
        self.write(self.root, "idea_set.json", output)
        code, revised = self.stage(self.root, "core")
        self.assertEqual((0, "ok", 2), (code, revised["status"], revised["generation_attempts"]), revised)
        for idea in output["ideas"]:
            self.assertIn(idea["working_title"], (self.root / "RESULT.md").read_text())
        request = json.loads((self.root / "request.json").read_text())
        for nested in ("hypothesis", "requires_user_confirmation"):
            invalid = copy.deepcopy(output)
            invalid["evidence_gap_translations"].append({"source_text": nested, "report_text": "unused nested status"})
            errors = validator.validate_idea_set(invalid, request, self.root / "idea_set.json")
            self.assertTrue(any(nested in error and "remove it" in error for error in errors), errors)

    def test_pending_asset_diagnostics_do_not_raise_on_invalid_shapes(self):
        """独立诊断只检查类型正确的依赖；错误容器仍由schema拒绝。"""
        request = self.prepare(self.root, 3)
        for field in ("required_assets", "assets_used", "assumptions"):
            for broken in (None, 7, "not an array", {}, [{}], [[]]):
                with self.subTest(field=field, broken=broken):
                    output = self.output(3)
                    output["ideas"][0]["production_feasibility"][field] = broken
                    errors = validator.validate_idea_set(output, request, self.root / "request.json")
                    self.assertTrue(any("schema" in error and field in error for error in errors), errors)
        output = self.output(3)
        output["gates"] = None
        self.assertTrue(validator.validate_idea_set(output, request, self.root / "request.json"))
        for broken in (None, {}, [{}]):
            malformed = copy.deepcopy(request)
            malformed["production_constraints"]["available_assets"] = broken
            self.assertEqual([], validator.production_asset_errors(output, malformed))

    def test_pending_assets_do_not_mask_other_production_rejections(self):
        """未来资源仍不能进入产能/改写，也不能遮住预算、排除项及假装使用错误。"""
        request = self.prepare(self.root, 3)
        request["exclusions"]["assets"] = ["A consenting guest"]
        request["production_constraints"]["total_time_minutes"] = 1
        for intent in ("capacity_plan", "rework_content"):
            with self.subTest(intent=intent):
                request["task_intent"] = intent
                output = self.output(3)
                output["task_intent"] = intent
                output["evidence_gap_translations"].append({"source_text": intent, "report_text": "production plan"})
                output["ideas"][0]["production_feasibility"].update(
                    required_assets=["A consenting guest"], assets_used=["A consenting guest"])
                errors = validator.production_asset_errors(output, request)
                self.assertTrue(any("only shortlist intents" in e for e in errors), errors)
                self.assertTrue(any("assets_used must be a subset" in e for e in errors), errors)
                if intent == "capacity_plan":
                    errors = validator.validate_idea_set(output, request, self.root / "request.json")
                    for marker in ("required asset is excluded", "asset is excluded", "exceed budget"):
                        self.assertTrue(any(marker in e for e in errors), errors)

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
