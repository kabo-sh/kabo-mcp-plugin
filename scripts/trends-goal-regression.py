"""Regression coverage for request goals, cold starts, and allocated report references."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
RUNTIME = Path(__file__).resolve().parents[1] / 'skills'
PROFILE_FIXTURES = Path(__file__).resolve().parent / 'fixtures/creator-profile'


def module(platform, script):
    path = RUNTIME / f"research-{platform}-trends/scripts/{script}.py"
    spec = importlib.util.spec_from_file_location(f"regression_{platform}_{script}", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def inputs(platform):
    fmt = {"youtube": "youtube_video", "instagram": "instagram_reel", "tiktok": "tiktok_video"}[platform]
    request = {"schema_version": "trend-research-request.v3", "request_id": "goal-regression",
               "mode": "current_popular", "niche": "reviews and first looks of cozy and indie games",
               "platforms": [platform], "window": {"since": "2026-09-01T00:00:00Z", "until": "2026-10-20T00:00:00Z"},
               "formats": [fmt], "locale": {"region": None, "language": None},
               "creator_profile": {"handle": "owner", "signature_content": [
                   {"id": "career", "name": "Gaming blogging career advice", "topic": "blogging income",
                    "approach": "career advice", "weight": 1, "seed_terms": ["job", "could", "money", "over", "want"],
                    "seed_hashtags": [], "example_content_ids": []}]}}
    snapshot = {"schema_version": "public-content-snapshot.v1", "snapshot_id": "snap-goal",
                "observed_at": "2026-10-20T00:00:00Z", "platform": platform,
                "scope": {"window": {"start": "2026-09-01T00:00:00Z", "end": "2026-10-20T00:00:00Z"}},
                "source": {"coverage_complete": True, "source_mode": "fixture"},
                "creators": [{"creator_id": "a", "handle": "creator_a"}, {"creator_id": "b", "handle": "creator_b"}],
                "items": [{"content_id": cid, "creator_id": author,
                           "url": f"https://example.invalid/{platform}/{cid}", "title": f"Cozy game review {cid}",
                           "published_at": "2026-10-01T00:00:00Z", "format": fmt,
                           "metrics": {"views": {"status": "available", "value": views}}}
                          for cid, author, views in (("one", "a", 500), ("two", "b", 300), ("unseated", "b", 900))]}
    gate = {"schema_version": "trend-relevance-gate.v1", "items": [
        {"content_key": f"{platform}:{cid}", "relevance": "direct"} for cid in ("one", "two", "unseated")]}
    allocation = {"schema": "signature-content-allocation.v1", "rule_version": "signature-allocation.v1",
                  "slots": [{"content_key": f"{platform}:one", "signature_content_id": "career", "rank": 1},
                            {"content_key": f"{platform}:two", "signature_content_id": None, "rank": 2}],
                  "per_content": {"career": {"quota": 2, "filled": 1}}, "shortfall": 0}
    synthesis = {"schema_version": "trend-research-synthesis.v3.3", "request_id": request["request_id"],
                 "report_id": "report-goal", "status": "partial", "overview": {
                     "title": "Cozy game reviews", "summary": "Compare the reviewed games.", "key_findings": [],
                     "next_action": "Try a first-look review."}, "featured_content_refs": ["one", "two"],
                 "patterns": [], "emerging_creators": [], "data_gaps": []}
    return request, snapshot, gate, allocation, synthesis


class GoalAndColdStartTest(unittest.TestCase):
    def test_current_goal_queries_do_not_need_historical_seeds(self):
        for platform in ("instagram", "tiktok", "youtube"):
            with self.subTest(platform=platform):
                req, *_ = inputs(platform)
                script = "validate_tiktok_query_plan" if platform == "tiktok" else "validate_query_plan"
                validator = module(platform, script)
                queries = ["cozy game reviews", "indie game first impressions"]
                plan = {"schema_version": "tiktok-trend-query-plan.v1" if platform == "tiktok" else "trend-query-plan.v1",
                        "request_id": req["request_id"], "intents": [
                            {"intent_id": str(n), "search_query": q} for n, q in enumerate(queries)]}
                validator.validate(plan)
                validator.validate_against_request(plan, req)
                req["creator_profile"]["excluded_topics"] = ["cozy game"]
                with self.assertRaisesRegex(ValueError, "excluded"):
                    validator.validate_against_request(plan, req)

    def test_topic_eligibility_is_independent_of_historical_class_match(self):
        for platform in ("instagram", "tiktok", "youtube"):
            with self.subTest(platform=platform):
                gate = {"schema_version": "trend-relevance-gate.v3", "platform": platform, "items": [
                    {"content_key": "on-topic", "signature_content_id": None,
                     "semantic_scores": {"topic_relevance": 95, "locale_fit": 100, "creator_transferability": 70}},
                    {"content_key": "off-topic", "signature_content_id": "career",
                     "semantic_scores": {"topic_relevance": 10, "locale_fit": 100, "creator_transferability": 100}}]}
                self.assertEqual({"on-topic": "direct", "off-topic": "reject"},
                                 module(platform, "trend_gate_contract").classifications(gate))
                output = {"request_id": "goal", "platform": platform,
                          "subject": {"niche": "cozy game reviews"}, "items": []}
                header = json.loads(next(module(platform, "project_relevance_gate_input").table_parts(output))[1])
                self.assertIn("subject.niche", header["topic_relevance_rule"])
                self.assertEqual("cozy game reviews", header["subject"]["niche"])

    def test_missing_classes_keep_reliable_fields_without_inventing_a_topic(self):
        for platform in ("instagram", "tiktok", "youtube"):
            with self.subTest(platform=platform):
                profile = json.loads((PROFILE_FIXTURES / f"{platform}.json").read_text())
                profile.pop("effectiveContentProfile", None)
                profile["contentProfile"].update(signatureContent=[], signatureContentStatus="no_qualifying_group")
                profile["contentProfile"]["language"] = {"primary": "pt", "confidence": "high", "accepted": ["pt"]}
                req = inputs(platform)[0]
                req["creator_profile"] = {"handle": profile["account"]["handle"]}
                intake = module(platform, "attach_creator_profile")
                attached, receipt = intake.attach(req, profile, platform)
                self.assertTrue(receipt["attached"])
                self.assertEqual(req["niche"], attached["niche"])
                self.assertEqual("pt", attached["creator_profile"]["content_language"])
                self.assertEqual(profile["account"]["audienceCount"], attached["creator_profile"]["audience_count"])
                self.assertNotIn("signature_content", attached["creator_profile"])
                profile["contentProfile"]["language"]["confidence"] = "low"
                self.assertNotIn("content_language", intake.attach(req, profile, platform)[0]["creator_profile"])
                profile["contentProfile"] = None
                self.assertFalse(intake.attach(req, profile, platform)[1]["attached"])

    def test_cold_start_excludes_known_ads_and_self_but_keeps_unknowns(self):
        for platform in ("instagram", "tiktok", "youtube"):
            with self.subTest(platform=platform):
                req = {"creator_profile": {"handle": "owner"}}
                own = {"content_key": "own", "author": {"handle": "owner"}, "channel": {"id": "owner"}}
                candidates = {"candidate_set_id": "set", "items": [own, {"content_key": "ad", "is_ad": True},
                                                                          {"content_key": "unknown"}]}
                result = module(platform, "filter_candidate_eligibility").filter_set(req, candidates, platform)
                self.assertEqual([{"content_key": "unknown"}], result["items"])
                self.assertFalse(result["eligibility"]["profile_fields_attached"])
                self.assertEqual([], result["eligibility"]["backfilled"])
                self.assertEqual("set", result["candidate_set_id"])


class ReportSelectionTest(unittest.TestCase):
    def test_null_class_is_selected_but_unseated_rows_cannot_escape_via_any_section(self):
        for platform in ("instagram", "tiktok", "youtube"):
            with self.subTest(platform=platform):
                req, snapshot, gate, allocation, synthesis = inputs(platform)
                analyzer = module(platform, "analyze_public_snapshot")
                analysis = analyzer.analyze(snapshot, "trend", None, request=req, relevance_gate=gate, allocation=allocation)
                self.assertEqual({"one", "two"}, set(analysis["selected_content_ids"]))
                self.assertEqual(3, len(analysis["ranked_content"]))
                self.assertIsNone(next(r for r in analysis["ranked_content"] if r["content_id"] == "two")["signature_content_id"])
                composer = module(platform, "compose_report")
                validator = module(platform, "validate_output")
                report = composer.compose(req, snapshot, analysis, synthesis)
                self.assertEqual([], validator.validate(report, req, analysis))
                for section in ("featured_content_refs", "patterns", "emerging_creators"):
                    bad = copy.deepcopy(synthesis)
                    if section == "featured_content_refs":
                        bad[section].append("unseated")
                    else:
                        bad[section] = [{"content_refs": ["unseated"]}]
                    with self.subTest(section=section), self.assertRaisesRegex(ValueError, "outside the allocation"):
                        composer.compose(req, snapshot, analysis, bad)
                bad_report = copy.deepcopy(report)
                injected = {**report["top_content"][-1], "rank": 3, "content_id": "unseated"}
                bad_report["top_content"].append(injected)
                self.assertTrue(any("outside the allocation" in e for e in validator.validate(bad_report, req, analysis)))
                # 直接篡改入选清单也不能在报告里重复同一创作者。
                duplicate_analysis = copy.deepcopy(analysis)
                duplicate_analysis["selected_content_ids"].append("unseated")
                self.assertTrue(any("multiple allocated videos" in e for e in validator.validate(bad_report, req, duplicate_analysis)))
                with self.assertRaisesRegex(ValueError, "multiple allocated videos"):
                    composer.compose(req, snapshot, duplicate_analysis,
                                     {**synthesis, "featured_content_refs": ["one", "two", "unseated"]})
                legacy = {k: v for k, v in analysis.items() if k != "selected_content_ids"}
                with self.assertRaisesRegex(ValueError, "regenerate analysis"):
                    composer.compose(req, snapshot, legacy, synthesis)

    def test_empty_allocation_is_not_replaced_with_the_ranked_pool(self):
        for platform in ("instagram", "tiktok", "youtube"):
            req, snapshot, gate, allocation, synthesis = inputs(platform)
            allocation.update(slots=[], per_content={"career": {"quota": 2, "filled": 0}}, shortfall=2)
            analyzer = module(platform, "analyze_public_snapshot")
            analysis = analyzer.analyze(snapshot, "trend", None, request=req, relevance_gate=gate, allocation=allocation)
            self.assertEqual([], analysis["selected_content_ids"])
            with self.assertRaisesRegex(ValueError, "outside the allocation"):
                module(platform, "compose_report").compose(req, snapshot, analysis, synthesis)
            empty = {**synthesis, "featured_content_refs": []}
            report = module(platform, "compose_report").compose(req, snapshot, analysis, empty)
            self.assertEqual([], module(platform, "validate_output").validate(report, req, analysis))


if __name__ == "__main__":
    unittest.main()
