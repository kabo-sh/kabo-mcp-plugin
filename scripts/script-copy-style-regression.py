#!/usr/bin/env python3
"""Copy style that takes many rounds: generic first drafts, samples not followed, rejections answered
with another round in the same style. The rules are pinned here so an edit cannot drop them, and the
validator must refuse copy that repeats wording the creator already rejected.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/create-script-and-packaging"
IDEAS = ROOT / "skills/develop-content-ideas"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_script_package", SKILL / "scripts/validate_script_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CopyStyleRules(unittest.TestCase):
    def test_style_reference_is_routed_and_read(self):
        skill = (SKILL / "SKILL.md").read_text()
        self.assertIn("references/copy-style.md", skill)
        self.assertIn("a style the creator did not state is not a missing input", skill)
        self.assertIn("copy-style.md", (SKILL / "references/topic-drafts.md").read_text())

    def test_sample_rejection_and_default_rules(self):
        text = (SKILL / "references/copy-style.md").read_text()
        for rule in ("the sample is the specification", "name the two or three\ntraits you are matching",
                     "two or three short directions", "ask one short question",
                     "must change the identified dimension visibly", "stays banned for the rest of the thread",
                     "concise by default", "creator's language"):
            self.assertIn(rule, text)

    def test_gate_no_longer_asks_for_voice_before_writing(self):
        rules = (SKILL / "references/package-rules.md").read_text()
        self.assertNotIn("Creator voice examples or prohibited language", rules)
        self.assertIn("Do not ask for voice examples or a tone before writing", rules)

    def test_unexplained_idea_rejection_identifies_a_dimension(self):
        text = (IDEAS / "references/request-boundaries.md").read_text()
        self.assertIn("A rejection without a reason", text)
        self.assertIn("Do not answer an unexplained rejection with another batch in the same mould", text)


class RejectedWording(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()

    def test_copy_cannot_repeat_rejected_wording(self):
        request = {"creative_direction": {"status": "partial", "tone": "calm, premium",
                                          "voice_rules": [], "banned_phrases": ["Level up", "game changer"]}}
        package = {"hook_options": [{"text": "This GAME CHANGER fixes your mornings"}],
                   "script": {"beats": [{"spoken": "Slow mornings, sharper days."}]},
                   "packaging": {"caption": "Quiet routines"},
                   "input_snapshot": {"creative_direction": request["creative_direction"]}}
        self.assertEqual(["game changer"], self.validator.rejected_wording_in_copy(package, request))
        package["hook_options"][0]["text"] = "Three quiet changes to your mornings"
        self.assertEqual([], self.validator.rejected_wording_in_copy(package, request))

    def test_missing_tone_does_not_force_needs_input(self):
        source = (SKILL / "scripts/validate_script_package.py").read_text()
        self.assertNotIn('(request.get("creative_direction") or {}).get("status") == "missing")', source)


if __name__ == "__main__":
    unittest.main()
