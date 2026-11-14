#!/usr/bin/env python3
"""Production bad cases where ideas stopped short of the request.

I024/I035: right after an account review in the same conversation, the ideas run said the account
material was missing and returned no ideas. I032/I033: the creator handed over the choice of niche
("help me choose a niche"), and the reply asked them to pick among three directions instead.
Pre case 3 (thread 6da25300): "我做恐怖故事频道，推荐 3 个视频选题，然后把最强的那个写成脚本。", the host asked for
the platform, the creator answered "YouTube Shorts", and the reply ended at "reply with a number" with no
script. The request now records generation_basis.follow_on and the export receipt names the idea to script.
These tests drive the real prep/core entry points; they do not grade creative quality.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/develop-content-ideas"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL / "scripts"))
import validate_ideas as validator

FIXTURE = json.loads((ROOT / "scripts/fixtures/ideas-continuation.json").read_text())

REVIEW_REQUEST = ("Review this youtube account in depth: https://www.youtube.com/channel/UCHg6z6ZIWHbV0hMJx0ieHlg. "
                  "Explain its content performance and give evidence-backed recommendations.")
REVIEW_REPLY = ("# Deep account review\n\nThe channel's cinematic character-conflict Shorts lead its recent window; "
                "explainer uploads trail them. Recommendation: test more two-character conflicts with a reveal "
                "in the last three seconds.\n\nData gaps: retention curves are private.")
IDEAS_REQUEST = "Develop five cinematic character-conflict Shorts based on the review."


class Followthrough(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def write(self, name, value, root=None):
        path = (root or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return path

    def run_script(self, *args):
        result = subprocess.run([sys.executable, "-B", *map(str, args)], capture_output=True, text=True)
        self.assertTrue(result.stdout, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def stage(self, run, stage, *flags):
        self.run = run
        return self.run_script(SKILL / "scripts/run_ideas_stages.py", stage, "--run-dir", run, *flags)

    def ideas(self, count, data_gaps, basis="brief_based", run=None):
        request = json.loads(((run or self.run) / "request.json").read_text())
        output = copy.deepcopy(FIXTURE["idea_set"])
        output.update(request_id=request["request_id"], task_intent=request["task_intent"],
                      source_mode=request["source_mode"])
        output["ideas"] = []
        for rank in range(1, count + 1):
            idea = copy.deepcopy(FIXTURE["idea"])
            idea.update(idea_id=f"idea-{rank:03d}", rank=rank, evidence_basis=basis,
                        platforms=list(request["platform_targets"]),
                        working_title=f"Two strangers, one locked door ({rank})")
            idea["production_feasibility"].update(required_assets=[], assets_used=[])
            output["ideas"].append(idea)
        output["evidence_summary"]["data_gaps"] = data_gaps
        output["evidence_gap_translations"] = [{"source_text": gap, "report_text": gap} for gap in data_gaps]
        return output

    # --- I024 / I031 / I035: account review already delivered in this conversation -----------------

    def account_route(self, run, reference_index=1, kind="account_review"):
        messages = self.write("visible.json", {"messages": [
            {"role": "user", "content": REVIEW_REQUEST},
            {"role": "assistant", "content": REVIEW_REPLY},
            {"role": "user", "content": IDEAS_REQUEST},
        ]}, run)
        quote = REVIEW_REPLY if reference_index == 1 else REVIEW_REQUEST
        self.write("reference-quote.txt", quote, run)
        self.write("current-query.txt", IDEAS_REQUEST, run)
        return self.run_script(
            SKILL / "scripts/prepare_conversation_inputs.py", "--messages", messages,
            "--reference-index", reference_index, "--reference-quote-file", run / "reference-quote.txt",
            "--brief-file", run / "current-query.txt", "--idea-count", 5, "--platform", "youtube",
            "--language", "en", "--continuation-quote", "based on the review", "--reference-kind", kind,
            "--run-dir", run)

    def test_account_review_in_conversation_reaches_five_ideas(self):
        """I035: the visible deep review satisfies the account requirement; five ideas are delivered."""
        run = self.root / "i035"
        code, helper = self.account_route(run)
        self.assertEqual((0, "ok"), (code, helper["status"]), helper)
        intent = json.loads((run / "intent.json").read_text())
        self.assertEqual(["account"], intent["generation_basis"]["required_sources"])
        code, prep = self.stage(run, "prep", "--intent", run / "intent.json",
                                "--conversation-context", run / "conversation-source.json")
        self.assertEqual((0, "ok", "ready_for_generation"), (code, prep["status"], prep["decision"]["status"]), prep)
        self.assertEqual(["account"], prep["decision"]["available_sources"])
        self.assertEqual([], prep["decision"]["missing_required_sources"])
        self.assertTrue(prep["decision"]["account_from_conversation"])
        gap = "Account figures come from the review earlier in this conversation and were not re-checked."
        self.write("idea_set.json", self.ideas(5, [gap]), run)
        code, core = self.stage(run, "core")
        self.assertEqual((0, "ok"), (code, core["status"]), core)
        report = (run / "RESULT.md").read_text()
        for rank in range(1, 6):
            self.assertIn(f"Two strangers, one locked door ({rank})", report)
        self.assertIn(gap, report)
        self.assertNotIn("use only your brief", report)

    def test_conversation_review_must_disclose_and_stay_unverified(self):
        """The bound review is not research: no data gap or a source_backed claim is a revision, not delivery."""
        run = self.root / "disclose"
        self.account_route(run)
        self.stage(run, "prep", "--intent", run / "intent.json", "--conversation-context", run / "conversation-source.json")
        request = json.loads((run / "request.json").read_text())
        errors = validator.validate_idea_set(self.ideas(5, []), request, run / "idea_set.json")
        self.assertTrue(any("not re-checked" in error for error in errors), errors)
        errors = validator.validate_idea_set(self.ideas(5, ["Not re-checked."], basis="source_backed"), request,
                                             run / "idea_set.json")
        self.assertTrue(any("not research evidence" in error or "evidence_refs" in error for error in errors), errors)

    def test_account_review_kind_must_point_at_the_assistant_review(self):
        """A user message cannot be relabelled as an account review to unlock the account requirement."""
        code, helper = self.account_route(self.root / "user", reference_index=0)
        self.assertEqual((1, "invalid_input"), (code, helper["status"]), helper)
        self.assertIn("assistant message", helper["errors"][0])

    def test_ordinary_chat_still_cannot_replace_account_evidence(self):
        """Without the account_review kind, chat context keeps the missing-source block (unchanged rule)."""
        run = self.root / "example"
        self.account_route(run, kind="example")
        intent = json.loads((run / "intent.json").read_text())
        intent.update(task_intent="open_shortlist")
        intent["generation_basis"]["required_sources"] = ["account"]
        (run / "intent.json").write_text(json.dumps(intent))
        code, prep = self.stage(run, "prep", "--intent", run / "intent.json",
                                "--conversation-context", run / "conversation-source.json")
        self.assertEqual("blocked_missing_required_source", prep["decision"]["status"], prep)

    # --- I032 / I033: the creator delegated the niche choice --------------------------------------

    def delegated_intent(self, brief, quote, topic, count=10):
        intent = copy.deepcopy(FIXTURE["intent"])
        intent.update(idea_count=count, platform_targets=["youtube"], task_intent="brief_only")
        intent["user_brief"]["text"] = brief
        intent["exclusions"] = {"topics": [], "claims": [], "formats": [], "assets": []}
        intent["production_constraints"] = {"status": "absent", "total_time_minutes": None, "time_per_item": None,
                                            "budget": None, "available_assets": [], "filming_mode": None,
                                            "editing_capacity": None, "publishing_cadence": None}
        basis = {"direct_topic": None, "required_sources": [], "allow_brief_fallback": False}
        if quote is not None:
            basis["delegated_topic"] = {"quote": quote, "topic": topic}
        intent["generation_basis"] = basis
        return intent

    def test_delegated_niche_choice_generates_with_a_stated_assumption(self):
        """I033: 'Help me choose a niche' → the assistant picks one, states it, and delivers ten ideas."""
        run = self.root / "i033"
        brief = "Help me choose a niche, then create 10 high-potential topic ideas."
        topic = "psychology and self-improvement"
        self.write("intent.json", self.delegated_intent(brief, "Help me choose a niche", topic), run)
        code, prep = self.stage(run, "prep", "--intent", run / "intent.json")
        self.assertEqual((0, "ok", "ready_for_generation"), (code, prep["status"], prep["decision"]["status"]), prep)
        self.assertEqual(topic, prep["decision"]["delegated_topic"])
        request = json.loads((run / "request.json").read_text())
        silent = validator.validate_idea_set(self.ideas(10, []), request, run / "idea_set.json")
        self.assertTrue(any("assumed niche" in error for error in silent), silent)
        gap = f"You asked me to choose the niche, so I assumed {topic}; tell me if you want another."
        self.write("idea_set.json", self.ideas(10, [gap]), run)
        code, core = self.stage(run, "core")
        self.assertEqual((0, "ok"), (code, core["status"]), core)
        self.assertIn(topic, (run / "RESULT.md").read_text())

    def test_chinese_delegation_span_is_accepted(self):
        """A short delegation such as 你帮我选领域 is a valid verbatim span in any language."""
        run = self.root / "zh"
        intent = self.delegated_intent("你帮我选领域，然后给我 10 个选题", "你帮我选领域", "心理学与自我提升")
        intent.update(report_language="zh-CN", language_targets=["zh-CN"])
        self.write("intent.json", intent, run)
        code, prep = self.stage(run, "prep", "--intent", run / "intent.json")
        self.assertEqual("ready_for_generation", prep.get("decision", {}).get("status"), prep)

    def test_without_delegation_a_bare_request_still_asks_for_a_topic(self):
        """'write 10 viral topic ideas' with no niche and no delegation keeps needs_selection_context."""
        run = self.root / "bare"
        self.write("intent.json", self.delegated_intent("write a 10 viral topic idea", None, None), run)
        code, prep = self.stage(run, "prep", "--intent", run / "intent.json")
        self.assertEqual("needs_correction", prep["status"], prep)
        self.assertTrue(any("brief_only requires" in json.dumps(issue) for issue in prep["issues"]), prep)

    def test_delegation_cannot_be_invented_or_generic(self):
        """The delegation quote must be the user's words, and the chosen niche must be a real topic."""
        brief = "Help me choose a niche, then create 10 high-potential topic ideas."
        for quote, topic, needle in (("you can pick anything for me", "personal finance", "delegated_topic.quote"),
                                     ("Help me choose a niche", "youtube shorts ideas", "concrete niche")):
            with self.subTest(needle=needle):
                run = self.root / needle.replace(" ", "-")
                self.write("intent.json", self.delegated_intent(brief, quote, topic), run)
                code, prep = self.stage(run, "prep", "--intent", run / "intent.json")
                self.assertEqual("needs_correction", prep["status"], prep)
                self.assertIn(needle, json.dumps(prep))

    def test_delegation_does_not_override_a_literal_topic(self):
        """When the user did name a topic, it stays the topic; delegated_topic is rejected."""
        intent = self.delegated_intent("You choose the angle: 10 sourdough shaping ideas.", "You choose the angle",
                                       "baking science")
        intent["generation_basis"]["direct_topic"] = "sourdough shaping"
        errors = validator.validate_authored_intent(intent)
        self.assertTrue(any("delegated_topic is only for a brief without its own topic" in e for e in errors), errors)

    # --- Pre case 3: "three ideas, then a script for the strongest" across a platform question ------

    HORROR_TURN_1 = "我做恐怖故事频道，推荐 3 个视频选题，然后把最强的那个写成脚本。"
    HORROR_TURN_2 = "YouTube Shorts"
    HORROR_FOLLOW_ON = "然后把最强的那个写成脚本"

    def horror_intent(self, follow_on_quote):
        intent = self.delegated_intent(f"{self.HORROR_TURN_1}\n{self.HORROR_TURN_2}", None, None, count=3)
        intent.update(task_intent="open_shortlist", report_language="zh-CN", language_targets=["zh-CN"])
        intent["generation_basis"]["direct_topic"] = "恐怖故事"
        if follow_on_quote is not None:
            intent["generation_basis"]["follow_on"] = {"deliverable": "script", "quote": follow_on_quote}
        return intent

    def deliver(self, run, follow_on_quote):
        self.write("intent.json", self.horror_intent(follow_on_quote), run)
        code, prep = self.stage(run, "prep", "--intent", run / "intent.json")
        self.assertEqual((0, "ok", "ready_for_generation"), (code, prep["status"], prep["decision"]["status"]), prep)
        ideas = self.ideas(3, ["没有频道历史表现数据"], run=run)
        ideas["report_language"] = "zh-CN"
        ideas["overview"]["recommended_candidate_ids"] = ["idea-001"]
        self.write("idea_set.json", ideas, run)
        code, core = self.stage(run, "core")
        self.assertEqual((0, "ok"), (code, core["status"]), core)
        code, receipt = self.run_script(SKILL / "scripts/deliver_ideas.py", "--run-dir", run)
        self.assertEqual((0, "validated"), (code, receipt["status"]), receipt)
        self.assertEqual((run / "RESULT.md").read_text(), (run / "FINAL_IDEAS.md").read_text())
        return receipt

    def test_platform_answer_keeps_the_script_follow_on(self):
        """The receipt names the recommended idea and tells the host the turn continues to its script."""
        receipt = self.deliver(self.root / "case3", self.HORROR_FOLLOW_ON)
        self.assertEqual({"deliverable": "script", "quote": self.HORROR_FOLLOW_ON, "number": 1,
                          "idea_id": "idea-001", "title": "Two strangers, one locked door (1)"}, receipt["follow_on"])
        self.assertIn("create-script-and-packaging", receipt["next_action"])
        self.assertIn("same turn", receipt["next_action"])
        self.assertIn("emit_block", receipt["next_action"])

    def test_list_only_request_still_ends_at_selection(self):
        """Without a follow-on the receipt is unchanged: emit the list and stop."""
        receipt = self.deliver(self.root / "list-only", None)
        self.assertNotIn("follow_on", receipt)
        self.assertEqual("Call emit_block with block.type=markdown and block.path=report_path. Do not rewrite the report.",
                         receipt["next_action"])

    def test_follow_on_quote_must_be_the_creators_words(self):
        """A follow-on cannot be invented: its quote must appear in user_brief.text."""
        errors = validator.validate_authored_intent(self.horror_intent("then write a script for every idea"))
        self.assertTrue(any("follow_on.quote" in error for error in errors), errors)
        errors = validator.validate_authored_intent(self.horror_intent(self.HORROR_FOLLOW_ON))
        self.assertFalse([error for error in errors if "follow_on" in error], errors)

    def test_skills_tell_the_host_to_continue_to_the_script(self):
        """Both Skills describe the same-turn hand-off the receipt triggers."""
        ideas = (SKILL / "SKILL.md").read_text() + (SKILL / "references/delivery.md").read_text()
        scripts = (ROOT / "skills/create-script-and-packaging/SKILL.md").read_text()
        self.assertIn("generation_basis.follow_on", ideas)
        self.assertIn("When the receipt has `follow_on`", ideas)
        self.assertIn("(`follow_on.title`)", scripts)


if __name__ == "__main__":
    unittest.main()
