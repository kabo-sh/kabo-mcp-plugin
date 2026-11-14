#!/usr/bin/env python3
"""Production script bad cases: changed or invented facts, partial delivery, unreadable links, failed saves.

S149 turned the creator's "domani" (tomorrow) into "oggi" (today); S094 turned "subir de nivel"
(level up) into "bajar de nivel"; S072 and S085 stated facts about real teams and a company that
nobody supplied. check_user_facts.py must stop each of these drafts and accept the corrected one.
I023, S004 and the save failures are instruction rules; their wording is pinned below so a later
edit cannot silently drop them.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/create-script-and-packaging"
IDEAS = ROOT / "skills/develop-content-ideas"
CHECK = SKILL / "scripts/check_user_facts.py"


class CreatorFacts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def check(self, facts, draft):
        (self.root / "facts.json").write_text(json.dumps(facts, ensure_ascii=False))
        (self.root / "draft.md").write_text(draft)
        result = subprocess.run([sys.executable, "-B", str(CHECK), "--facts", str(self.root / "facts.json"),
                                 "--draft", str(self.root / "draft.md")], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_s149_tomorrow_cannot_become_today(self):
        source = "Domani il ministro Crosetto riferisce al Copasir sui nuovi aiuti militari all'Ucraina."
        facts = {"source_text": source, "facts": [
            {"source": "Domani il ministro Crosetto riferisce al Copasir", "keep": ["Domani", "Crosetto", "Copasir"]}]}
        drifted = self.check(facts, "Nuovi aiuti militari all'Ucraina: oggi Crosetto riferisce al Copasir.")
        self.assertEqual("needs_correction", drifted["status"])
        self.assertIn("'Domani'", drifted["errors"][0])
        fixed = self.check(facts, "Nuovi aiuti militari all'Ucraina: domani Crosetto riferisce al Copasir.")
        self.assertEqual("ok", fixed["status"], fixed)

    def test_s094_level_up_cannot_become_level_down(self):
        source = ("PERO leer que Carl y Donut llegaron al nivel 3, con un horario recortado, consiguieron manager "
                  "y tuvieron que completar dos \"misiones secundarias\" para poder subir de nivel")
        facts = {"source_text": source, "facts": [
            {"source": "llegaron al nivel 3", "keep": ["nivel 3"]},
            {"source": "para poder subir de nivel", "keep": ["subir de nivel"]}]}
        drifted = self.check(facts, "llegaron al nivel 3 ... completar dos misiones secundarias para poder bajar de nivel")
        self.assertEqual("needs_correction", drifted["status"])
        self.assertTrue(any("subir de nivel" in error for error in drifted["errors"]), drifted)
        fixed = self.check(facts, "llegaron al nivel 3 ... completar dos misiones secundarias para poder subir de nivel")
        self.assertEqual("ok", fixed["status"], fixed)

    def test_s072_s085_unsupplied_real_world_claims_need_a_basis(self):
        source = "Quiero hablar de la salida de CR7 y su comparación con Messi"
        draft = ("Argentina también sufrirá cuando Messi se marche, pero ya empezó a repartir el protagonismo.\n"
                 "¿Qué selección sufrirá más?")
        claim = "pero ya empezó a repartir el protagonismo"
        unsupported = self.check({"source_text": source, "facts": [], "claims": [{"text": claim}]}, draft)
        self.assertEqual("needs_correction", unsupported["status"])
        self.assertIn("has no basis", unsupported["errors"][0])
        forged = self.check({"source_text": source, "facts": [],
                             "claims": [{"text": claim, "basis": "creator", "support": "Argentina ya repartió"}]}, draft)
        self.assertEqual("needs_correction", forged["status"])
        asked = self.check({"source_text": source, "facts": [],
                            "claims": [{"text": "¿Qué selección sufrirá más?", "basis": "question"}]},
                           "¿Qué selección sufrirá más?")
        self.assertEqual("ok", asked["status"], asked)
        sofi = self.check({"source_text": "SOFI", "facts": [], "claims": [
            {"text": "SoFi is really three connected businesses", "basis": "evidence", "ref": ""}]},
            "SoFi is really three connected businesses.")
        self.assertEqual("needs_correction", sofi["status"])

    def test_facts_must_come_from_the_creator_and_translations_keep_numbers(self):
        source = "The launch is on 12 March and costs 49 dollars."
        invented = self.check({"source_text": source, "facts": [{"source": "launch is free", "keep": ["free"]}]},
                              "The launch is free.")
        self.assertIn("copied exactly from source_text", invented["errors"][0])
        translated = self.check({"source_text": source, "facts": [
            {"source": "costs 49 dollars", "keep": ["49"], "rendered": "cuesta 39 dólares"}]},
            "El lanzamiento cuesta 39 dólares.")
        self.assertIn("lost the number", translated["errors"][0])
        omitted = self.check({"source_text": source, "facts": [{"source": "12 March", "omitted": True}]}, "Launch.")
        self.assertIn("without a reason", omitted["errors"][0])


class InstructionRules(unittest.TestCase):
    """Rules the model applies; pin their wording where the case would recur."""

    def text(self, path):
        return " ".join(path.read_text().split())

    def test_i023_every_part_of_a_multi_part_request(self):
        for skill in (SKILL, IDEAS):
            with self.subTest(skill=skill.name):
                body = self.text(skill / "SKILL.md")
                self.assertIn("**Deliver every part of the request.**", body)
                self.assertIn("completes an earlier request", body)
                self.assertIn("for the strongest", body)

    def test_s004_unreadable_link_is_reported_not_templated(self):
        body = self.text(SKILL / "SKILL.md")
        self.assertIn("**Links that cannot be read.**", body)
        self.assertIn("Do not answer with generic templates", body)

    def test_failed_save_keeps_the_shown_draft(self):
        saving = self.text(SKILL / "references/saved-kabo-scripts.md")
        self.assertIn("the draft you already showed stays the deliverable", saving)
        self.assertIn("never say it was saved", saving)

    def test_facts_reference_is_routed_and_runs_the_check(self):
        body = self.text(SKILL / "SKILL.md")
        self.assertIn("`references/creator-facts.md`", body)
        self.assertIn("`scripts/check_user_facts.py`", body)
        reference = self.text(SKILL / "references/creator-facts.md")
        self.assertIn("scripts/check_user_facts.py' --facts", reference)
        self.assertIn('"tomorrow" stays tomorrow', reference)


if __name__ == "__main__":
    unittest.main()
