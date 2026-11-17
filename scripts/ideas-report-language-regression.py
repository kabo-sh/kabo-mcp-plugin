#!/usr/bin/env python3
"""Fixed report labels follow the creator's language: Traditional Chinese gets its own catalog, and a language
without a catalog (Bosnian) renders the labels the model translated instead of English (I003, I011)."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('count_fixture', ROOT / 'scripts/ideas-count-regression.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
SKILL = fixture.SKILL
sys.path.insert(0, str(SKILL / 'scripts'))
import report_language  # noqa: E402

SIMPLIFIED = ['为什么适合', '先选它的原因', '开口就说', '怎么拍', '制作量', '证据边界', '可供选择']


class ReportLanguage(unittest.TestCase):
    setUp = fixture.IdeaCounts.setUp
    write = fixture.IdeaCounts.write
    stage = fixture.IdeaCounts.stage

    def run_core(self, language, translations=None, brief='Give me 3 AI sales workflow ideas for Instagram.'):
        intent = fixture.IdeaCounts.intent(self, 3)
        intent['report_language'] = language
        intent['user_brief']['text'] = brief
        path = self.write(self.root, 'intent.json', intent)
        code, prep = self.stage(self.root, 'prep', '--intent', path)
        self.assertEqual((0, 'ok'), (code, prep['status']), prep)
        ideas = fixture.IdeaCounts.output(self, 3)
        ideas['report_language'] = language
        ideas['evidence_gap_translations'] = translations or []
        self.write(self.root, 'idea_set.json', ideas)
        return self.stage(self.root, 'core')

    def export(self):
        result = subprocess.run([sys.executable, '-B', str(SKILL / 'scripts/deliver_ideas.py'), '--run-dir', str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return Path(json.loads(result.stdout)['report_path']).read_text(encoding='utf-8')

    def test_traditional_chinese_report_uses_traditional_labels(self):
        # I003: "Please reply in Traditional Chinese" produced Traditional ideas under Simplified labels.
        code, core = self.run_core('zh-TW', brief='請用繁體中文，給我 3 個 AI sales workflow 的影片選題。')
        self.assertEqual((0, 'ok'), (code, core['status']), core)
        report = self.export()
        for label in ['為什麼適合', '先選它的原因', '開口就說', '怎麼拍', '製作量', '證據邊界', '可供選擇']:
            self.assertIn(label, report)
        for label in SIMPLIFIED:
            self.assertNotIn(label, report)

    def test_traditional_catalog_covers_every_simplified_label(self):
        chinese = [key for key in report_language.CATALOG if any('一' <= c <= '鿿' for c in key)]
        self.assertEqual([], [key for key in chinese if key not in report_language.TRADITIONAL['labels']])
        self.assertEqual(set(report_language.CHINESE_VALUES), set(report_language.TRADITIONAL['values']))
        for tag in ('zh-TW', 'zh-HK', 'zh-Hant', 'zh-Hant-TW', 'zh-MO'):
            self.assertEqual('zh-hant', report_language.ui_locale({'report_language': tag}), tag)
        for tag in ('zh', 'zh-CN', 'zh-Hans', 'zh-SG'):
            self.assertEqual('zh', report_language.ui_locale({'report_language': tag}), tag)

    def test_language_without_catalog_renders_the_translated_labels(self):
        # I011: a Bosnian creator got English labels ("Why choose it first", "How to film").
        labels = report_language.ui_label_sources({'report_language': 'bs'})
        template = json.loads(subprocess.run([sys.executable, '-B', str(SKILL / 'scripts/report_language.py'), 'bs', '--template'],
                                             capture_output=True, text=True, check=True).stdout)
        self.assertEqual(sorted(labels), [row['source_text'] for row in template])
        self.assertTrue(all(row['report_text'] == '' for row in template))
        code, core = self.run_core('bs', brief='daj mi 3 ideje za AI sales workflow i kako da napravim klip')
        self.assertNotEqual('ok', core['status'], core)
        self.assertIn('do not substitute another language', json.dumps(core))
        bosnian = [{'source_text': source, 'report_text': source.replace('Why choose it first', 'Zašto prvo ovu')
                    .replace('How to film', 'Kako snimiti').replace('Film first', 'Prvo snimi') + ('' if source.endswith(' ') else '')}
                   for source in sorted(labels)]
        values = [{'source_text': value, 'report_text': value + ' (bs)'} for value in ('brief_only', 'open_shortlist', 'ready_for_selection')]
        self.root = self.root / 'second'
        code, core = self.run_core('bs', bosnian + values, brief='daj mi 3 ideje za AI sales workflow i kako da napravim klip')
        self.assertEqual((0, 'ok'), (code, core['status']), core)
        report = self.export()
        self.assertIn('Zašto prvo ovu', report)
        self.assertIn('Kako snimiti', report)
        self.assertNotIn('Why choose it first', report)
        self.assertNotIn('How to film', report)


if __name__ == '__main__':
    unittest.main()
