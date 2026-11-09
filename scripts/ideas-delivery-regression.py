#!/usr/bin/env python3
"""最终文件闸门、稳定编号及失败清理的执行回归。"""
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


class Delivery(unittest.TestCase):
    setUp = fixture.IdeaCounts.setUp
    write = fixture.IdeaCounts.write
    stage = fixture.IdeaCounts.stage
    intent = fixture.IdeaCounts.intent
    output = fixture.IdeaCounts.output
    prepare = fixture.IdeaCounts.prepare

    def export(self, root=None):
        result = subprocess.run([sys.executable, '-B', str(SKILL / 'scripts/deliver_ideas.py'),
                                 '--run-dir', str(root or self.root)], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def ready(self, count=3):
        self.prepare(self.root, count)
        ideas = self.output(count)
        self.write(self.root, 'idea_set.json', ideas)
        self.assertEqual('ok', self.stage(self.root, 'core')[1]['status'])
        return ideas

    def no_final(self):
        self.assertFalse((self.root / 'FINAL_IDEAS.md').exists())
        self.assertFalse((self.root / 'idea-delivery.json').exists())

    def test_all_counts_full_utf8_and_idempotent_export(self):
        for count in (3, 10, 15, 20):
            with self.subTest(count=count):
                self.root = self.root / str(count)
                ideas = self.ready(count)
                self.no_final()
                code, receipt = self.export()
                self.assertEqual(0, code, receipt)
                self.assertEqual('validated', receipt['status'])
                self.assertEqual(count, receipt['count'])
                self.assertEqual(list(range(1, count + 1)), [i['number'] for i in receipt['items']])
                self.assertEqual([i['idea_id'] for i in ideas['ideas']], [i['idea_id'] for i in receipt['items']])
                report = Path(receipt['report_path']).read_text(encoding='utf-8')
                self.assertEqual((self.root / 'RESULT.md').read_text(encoding='utf-8'), report)
                for idea in ideas['ideas']:
                    self.assertIn(idea['hook_preview']['opening_line'], report)
                    self.assertIn(idea['making_direction'], report)
                self.assertEqual(receipt, self.export()[1])

    def test_needs_revision_and_exhausted_budget_cannot_export(self):
        self.prepare(self.root, 20)
        self.write(self.root, 'idea_set.json', self.output(15))
        for expected in ('needs_revision', 'not_met'):
            self.assertEqual(expected, self.stage(self.root, 'core')[1]['status'])
            self.assertEqual(1, self.export()[0])
            self.no_final()

    def test_render_without_core_is_not_validation(self):
        self.ready()
        timing = json.loads((self.root / 'stage_timing.json').read_text(encoding='utf-8'))
        timing['core']['status'] = 'needs_revision'
        self.write(self.root, 'stage_timing.json', timing)
        self.assertEqual(1, self.export()[0])
        self.no_final()

    def test_tampered_report_removes_previous_final(self):
        self.ready()
        self.assertEqual(0, self.export()[0])
        (self.root / 'RESULT.md').write_text('Titles only')
        self.assertEqual(1, self.export()[0])
        self.no_final()

    def test_changed_input_removes_previous_final(self):
        ideas = self.ready()
        self.assertEqual(0, self.export()[0])
        ideas['ideas'][0]['hook_preview']['opening_line'] = 'A new unchecked opening'
        self.write(self.root, 'idea_set.json', ideas)
        self.assertEqual(1, self.export()[0])
        self.no_final()

    def test_missing_source_removes_previous_final(self):
        self.ready()
        self.assertEqual(0, self.export()[0])
        (self.root / 'request.json').unlink()
        self.assertEqual(1, self.export()[0])
        self.no_final()

    def test_changed_data_and_regenerated_report_cannot_reuse_core(self):
        ideas = self.ready()
        self.assertEqual(0, self.export()[0])
        ideas['ideas'][0]['hook_preview']['opening_line'] = 'A structurally valid but unchecked replacement'
        self.write(self.root, 'idea_set.json', ideas)
        from render_idea_report import concise
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        (self.root / 'RESULT.md').write_text(concise(ideas, request), encoding='utf-8')
        code, result = self.export()
        self.assertEqual(1, code)
        self.assertIn('Inputs differ', result['error'])
        self.no_final()

    def test_missing_core_digest_cannot_export(self):
        self.ready()
        timing = json.loads((self.root / 'stage_timing.json').read_text(encoding='utf-8'))
        del timing['core']['validated_input_sha256']
        self.write(self.root, 'stage_timing.json', timing)
        self.assertEqual(1, self.export()[0])
        self.no_final()

    def test_recommendations_do_not_reorder_visible_numbers(self):
        self.prepare(self.root, 5)
        ideas = self.output(5)
        ideas['overview']['recommended_candidate_ids'] = ['idea-001', 'idea-005', 'idea-003']
        ideas['ideas'].reverse()
        self.write(self.root, 'idea_set.json', ideas)
        self.assertEqual('ok', self.stage(self.root, 'core')[1]['status'])
        code, receipt = self.export()
        self.assertEqual(0, code, receipt)
        report = Path(receipt['report_path']).read_text(encoding='utf-8')
        positions = [report.index(f'### {n}. ') for n in range(1, 6)]
        self.assertEqual(sorted(positions), positions)
        self.assertEqual('idea-003', receipt['items'][2]['idea_id'])
        self.assertEqual('idea-005', receipt['items'][4]['idea_id'])

    def test_terminal_clarification_has_no_final_list(self):
        self.ready()
        timing = json.loads((self.root / 'stage_timing.json').read_text(encoding='utf-8'))
        timing['core']['status'] = 'delivered_terminal'
        self.write(self.root, 'stage_timing.json', timing)
        self.assertEqual(1, self.export()[0])
        self.no_final()


if __name__ == '__main__':
    unittest.main()
