#!/usr/bin/env python3
"""Validators reject leaks, not creator prose; display length is fitted by the script, not rewritten."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "skills/review-creator-account/scripts"))
import validate_creator_report as report  # noqa: E402
sys.path.insert(0, str(ROOT / "skills/review-creator-account-deep/scripts"))
from synthesis_contract import TextTooLong, fit_text  # noqa: E402


class CreatorReportChecks(unittest.TestCase):
    def test_shell_check_ignores_product_words_but_catches_commands(self):
        shell = dict(report.LINEAGE_PATTERNS)["shell invocation"]
        for prose in ("Use a curl cream for definition", "the node of the story", "bash the critics"):
            self.assertIsNone(shell.search(prose), prose)
        for command in ("curl -s https://x.test", "python3 drive.py report", "pip install pkg", "npx some-tool",
                        "node --version", "bash ./run.sh", "python -m http.server"):
            self.assertIsNotNone(shell.search(command), command)

    def test_hosts_in_fetched_public_text_may_be_quoted(self):
        envelopes = [{"connector_id": "public", "data": {"items": [
            {"caption": "Link in bio https://shop.example.app.br/#x", "download_url": "https://storage.example.com/a"}]}}]
        allowed = report.evidence_hosts({}) | report.public_text_hosts(envelopes)
        markdown = "Their link shop.example.app.br and shop.example.app, plus storage.example.com and api.vendor.io"
        self.assertEqual(report.foreign_hosts(markdown, allowed), ["storage.example.com", "api.vendor.io"])

    def test_service_records_and_sibling_sites_stay_foreign(self):
        envelopes = [{"data": {"items": [{"caption": "https://mybrand.co.uk"}]},
                      "result": {"artifact": {"description": "stored at files.example.net"}}}]
        allowed = report.evidence_hosts({}) | report.public_text_hosts(envelopes)
        foreign = report.foreign_hosts("mybrand.co.uk, scraper.co.uk, files.example.net", allowed)
        self.assertIn("files.example.net", foreign)
        self.assertTrue(any(host.startswith("scraper.") for host in foreign), foreign)
        self.assertFalse(any(host.startswith("mybrand.") for host in foreign), foreign)


class DisplayLength(unittest.TestCase):
    def test_sentence_then_word_boundary(self):
        self.assertEqual(fit_text("First sentence here. Second one goes on and on.", 30), "First sentence here.")
        self.assertEqual(fit_text("one two three four five six seven eight", 20), "one two three four…")
        self.assertEqual(fit_text("short", 20), "short")

    def test_bounded_copy_fits_every_listed_field(self):
        value = {"headline": "A" * 10 + ". " + "B" * 30, "patterns": [{"explanation": "word " * 20}]}
        error = TextTooLong([{"path": "synthesis.headline", "length": 42, "max_length": 20},
                             {"path": "synthesis.patterns[0].explanation", "length": 100, "max_length": 30}])
        fitted = error.bounded(value)
        self.assertEqual(fitted["headline"], "A" * 10 + ".")
        self.assertLessEqual(len(fitted["patterns"][0]["explanation"]), 30)
        self.assertEqual(value["headline"], "A" * 10 + ". " + "B" * 30)


if __name__ == "__main__":
    unittest.main()
