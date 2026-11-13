"""分片完整性、幂等和最终聚合修订的真实脚本回归。"""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('delivery_fixture', ROOT / 'scripts/ideas-delivery-regression.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Batches(fixture.Delivery):
    def payload(self, count, batch):
        output = self.output(count)
        plan = json.loads((self.root / 'idea_work_plan.json').read_text())
        ideas = output.pop('ideas')[(batch - 1) * 10:batch * 10]
        for idea in ideas:
            idea.pop('idea_id'); idea.pop('rank')
        payload = {'request_sha256': plan['request_sha256'], 'batch_id': batch, 'ideas': ideas}
        if batch == (count + 9) // 10:
            payload['report'] = {k: v for k, v in output.items() if k not in plan['metadata']}
        return payload

    def submit(self, payload):
        return self.stage(self.root, 'batch', '--input', self.write(self.root, 'batch.json', payload))

    def test_batch_counts_and_metadata_full_delivery(self):
        for count in (1, 2, 3, 5, 10, 15, 20):
            with self.subTest(count=count):
                self.root = self.root / str(count)
                request = self.prepare(self.root, count)
                for batch in range(1, (count + 9) // 10 + 1):
                    code, result = self.submit(self.payload(count, batch))
                    self.assertEqual(0, code, result)
                    self.assertFalse(result['delivery_ready'])
                    if result['missing_batches']:
                        self.assertFalse((self.root / 'idea_set.json').exists())
                        self.assertNotEqual(0, self.export()[0])
                code, result = self.stage(self.root, 'core')
                self.assertEqual('ok', result['status'], result)
                self.assertEqual(count, self.export()[1]['count'])
                data = json.loads((self.root / 'idea_set.json').read_text())
                self.assertEqual(request['request_id'], data['request_id'])
                self.assertEqual(list(range(1, count + 1)), [x['rank'] for x in data['ideas']])
                timing = json.loads((self.root / 'stage_timing.json').read_text())['core']
                self.assertEqual((count + 9) // 10, timing['initial_authoring_submissions'])

    def test_replay_out_of_order_and_conflicts(self):
        self.prepare(self.root, 20)
        p2 = self.payload(20, 2)
        self.assertEqual([1], self.submit(p2)[1]['missing_batches'])
        self.assertTrue(self.submit(p2)[1]['idempotent_replay'])
        p2['ideas'][0]['working_title'] = 'changed'
        self.assertNotEqual(0, self.submit(p2)[0])
        self.assertEqual('ready_for_core', self.submit(self.payload(20, 1))[1]['status'])
        before = (self.root / 'idea_set.json').read_bytes()
        self.assertTrue(self.submit(self.payload(20, 1))[1]['idempotent_replay'])
        self.assertEqual(before, (self.root / 'idea_set.json').read_bytes())

    def test_missing_batch_cannot_be_bypassed_with_handwritten_set(self):
        self.prepare(self.root, 20)
        self.submit(self.payload(20, 1))
        self.write(self.root, 'idea_set.json', self.output(20))
        self.assertEqual('failed', self.stage(self.root, 'core')[1]['status'])
        self.assertNotEqual(0, self.export()[0])

    def test_cross_request_rank_count_and_metadata_rejected(self):
        self.prepare(self.root, 20)
        original = self.payload(20, 1)
        bad = []
        p = copy.deepcopy(original);p['request_sha256'] = 'other';bad.append(p)
        p = copy.deepcopy(original);p['ideas'][0]['rank'] = 11;bad.append(p)
        p = copy.deepcopy(original);p['ideas'].append(p['ideas'][0]);bad.append(p)
        p = self.payload(20, 2);p['report']['request_id'] = 'other';bad.append(p)
        p = copy.deepcopy(original);p['batch_id'] = True;bad.append(p)
        for payload in bad:
            self.assertNotEqual(0, self.submit(payload)[0])
        self.assertFalse(json.loads((self.root / 'idea_work_plan.json').read_text())['submissions'])
        request = json.loads((self.root / 'request.json').read_text());request['request_id'] = 'changed'
        self.write(self.root, 'request.json', request)
        self.assertNotEqual(0, self.submit(original)[0])

    def test_duplicate_titles_repaired_once_after_full_merge(self):
        self.prepare(self.root, 20)
        p1 = self.payload(20, 1);p2 = self.payload(20, 2)
        p2['ideas'][0]['working_title'] = p1['ideas'][0]['working_title']
        self.submit(p1);self.submit(p2)
        first = self.stage(self.root, 'core')[1]
        self.assertEqual('needs_revision', first['status'])
        self.assertEqual(1, first['revision_remaining'])
        self.assertNotEqual(0, self.export()[0])
        self.assertNotEqual(0, self.submit(p2)[0])
        data = json.loads((self.root / 'idea_set.json').read_text())
        data['ideas'][10]['working_title'] = 'Unique revised title'
        self.write(self.root, 'idea_set.json', data)
        self.assertEqual('ok', self.stage(self.root, 'core')[1]['status'])
        self.assertEqual(20, self.export()[1]['count'])
        self.assertEqual('not_met', self.stage(self.root, 'core')[1]['status'])

    # --- Pre 2026-11-12 failure shapes: core needs_revision that the model could not repair ---

    def run_batches(self, count, mutate=None):
        self.prepare(self.root, count)
        result = None
        for batch in range(1, (count + 9) // 10 + 1):
            payload = self.payload(count, batch)
            if mutate:
                mutate(batch, payload)
            code, result = self.submit(payload)
            self.assertEqual(0, code, result)
        return result

    def test_last_batch_top_choice_is_promoted_to_rank_one(self):
        # 6/8 observed needs_revision were exactly "rank 1 must be the first recommended candidate":
        # the final batch recommends e.g. idea-003 while the script had fixed ranks to slots.
        for count, top in ((3, 'idea-003'), (15, 'idea-012'), (20, 'idea-017')):
            with self.subTest(count=count):
                self.root = self.root / f'top{count}'
                def mutate(batch, payload):
                    if 'report' in payload:
                        payload['report']['overview']['recommended_candidate_ids'] = [top, 'idea-001']
                result = self.run_batches(count, mutate)
                self.assertEqual('ready_for_core', result['status'])
                self.assertEqual({'idea_id': top, 'from_rank': int(top[-3:]), 'to_rank': 1},
                                 {k: result['rank_adjustment'][k] for k in ('idea_id', 'from_rank', 'to_rank')})
                code, core = self.stage(self.root, 'core')
                self.assertEqual((0, 'ok', 1), (code, core['status'], core['generation_attempts']), core)
                code, receipt = self.export()
                self.assertEqual(0, code, receipt)
                self.assertEqual(list(range(1, count + 1)), [i['number'] for i in receipt['items']])
                expected = [top] + [f'idea-{n:03d}' for n in range(1, count + 1) if f'idea-{n:03d}' != top]
                self.assertEqual(expected, [i['idea_id'] for i in receipt['items']])
                report = Path(receipt['report_path']).read_text(encoding='utf-8')
                self.assertIn(f'### 1. Workflow decision {top[-3:]} (first choice)', report.split('### 2. ')[0])

    def test_rank_error_message_names_both_ids(self):
        self.prepare(self.root, 5)
        data = self.output(5)
        data['overview']['recommended_candidate_ids'] = ['idea-004']
        self.write(self.root, 'idea_set.json', data)
        code, result = self.stage(self.root, 'core')
        self.assertEqual('needs_revision', result['status'])
        self.assertTrue(any("'idea-004'" in e and "'idea-001'" in e for e in result['errors']), result['errors'])

    def test_invalid_batch_is_rejected_locally_with_exact_paths(self):
        self.prepare(self.root, 20)
        self.assertEqual(0, self.submit(self.payload(20, 1))[0])
        bad = self.payload(20, 2)
        bad['ideas'][1]['evidence_basis'] = 'gut_feeling'
        del bad['ideas'][3]['hook_preview']
        bad['report']['overview']['recommended_candidate_ids'] = ['idea-099']
        bad['report']['bonus'] = True
        code, result = self.submit(bad)
        self.assertEqual((0, 'needs_revision', 'batch', False), (code, result['status'], result['stage'], result['accepted']), result)
        details = result['error_details']
        self.assertIn(('idea-012', 'evidence_basis'), {(d.get('idea_id'), d['path']) for d in details})
        self.assertTrue(any(d.get('idea_id') == 'idea-014' and 'hook_preview' in d['error'] for d in details), details)
        self.assertTrue(any('idea-099' in e for e in result['errors']))
        self.assertTrue(any("'bonus'" in e for e in result['errors']))
        self.assertEqual([2], result['missing_batches'])
        self.assertEqual(['1'], list(json.loads((self.root / 'idea_work_plan.json').read_text())['submissions']))
        self.assertFalse((self.root / 'idea_set.json').exists())
        code, result = self.submit(self.payload(20, 2))
        self.assertEqual((0, 'ready_for_core'), (code, result['status']), result)
        self.assertEqual('ok', self.stage(self.root, 'core')[1]['status'])

    def revision(self, edits):
        return self.stage(self.root, 'revise', '--input', self.write(self.root, 'revision.json', {'edits': edits}))

    def needs_revision_20(self):
        def mutate(batch, payload):
            if batch == 2:
                payload['ideas'][0]['working_title'] = self.payload(20, 1)['ideas'][0]['working_title']
        self.run_batches(20, mutate)
        code, first = self.stage(self.root, 'core')
        self.assertEqual((0, 'needs_revision'), (code, first['status']), first)
        return first

    def test_revise_applies_targeted_edit_without_rewriting_merged_set(self):
        first = self.needs_revision_20()
        self.assertEqual('revise', first['revise_command'][2])
        self.assertIn('edits', first['revision_template'])
        self.assertTrue(first['error_details'])
        before = json.loads((self.root / 'idea_set.json').read_text())
        code, result = self.revision([{'idea_id': 'idea-011', 'path': 'working_title', 'value': 'Unique revised title'}])
        self.assertEqual((0, 'ready_for_core', []), (code, result['status'], result['remaining_errors']), result)
        self.assertEqual([{'idea_id': 'idea-011', 'path': 'working_title', 'value': 'Unique revised title'}], result['applied'])
        after = json.loads((self.root / 'idea_set.json').read_text())
        self.assertEqual('Unique revised title', after['ideas'][10]['working_title'])
        after['ideas'][10]['working_title'] = before['ideas'][10]['working_title']
        self.assertEqual(before, after)
        timing = json.loads((self.root / 'stage_timing.json').read_text())['core']
        self.assertEqual(1, timing['generation_attempts'])
        code, core = self.stage(self.root, 'core')
        self.assertEqual((0, 'ok', 2), (code, core['status'], core['generation_attempts']), core)
        self.assertEqual(20, self.export()[1]['count'])
        self.assertEqual(1, self.revision([{'path': 'overview.headline', 'value': 'x'}])[0])

    def test_revise_rejects_bad_edits_atomically_and_dry_runs_leftovers(self):
        self.needs_revision_20()
        original = (self.root / 'idea_set.json').read_bytes()
        bad = [
            [{'idea_id': 'idea-011', 'path': 'working_title', 'value': 'ok'}, {'idea_id': 'idea-404', 'path': 'working_title', 'value': 'x'}],
            [{'idea_id': 'idea-011', 'path': 'rank', 'value': 1}],
            [{'path': 'request_id', 'value': 'other'}],
            [{'path': 'ideas[0].working_title', 'value': 'x'}],
            [{'idea_id': 'idea-011', 'path': 'content_outline[99].text', 'value': 'x'}],
            [{'idea_id': 'idea-011', 'path': 'working title', 'value': 'x'}],
            [{'idea_id': 'idea-011', 'path': 'working_title'}],
        ]
        for edits in bad:
            with self.subTest(edits=edits):
                code, result = self.revision(edits)
                self.assertEqual((0, 'needs_revision', []), (code, result['status'], result['applied']), result)
                self.assertTrue(result['edit_errors'])
                self.assertEqual(original, (self.root / 'idea_set.json').read_bytes())
        code, result = self.revision([{'idea_id': 'idea-005', 'path': 'evidence_basis', 'value': 'gut_feeling'},
                                      {'idea_id': 'idea-011', 'path': 'working_title', 'value': 'Unique revised title'}])
        self.assertEqual('needs_revision', result['status'])
        self.assertIn(('idea-005', 'evidence_basis'), {(d['idea_id'], d['path']) for d in result['error_details']})
        self.assertEqual(1, json.loads((self.root / 'stage_timing.json').read_text())['core']['generation_attempts'])
        original = self.payload(20, 1)['ideas'][4]['evidence_basis']
        code, result = self.revision([{'idea_id': 'idea-005', 'path': 'evidence_basis', 'value': original}])
        self.assertEqual('ready_for_core', result['status'], result)
        self.assertEqual('ok', self.stage(self.root, 'core')[1]['status'])

    def test_revise_recommendation_edit_keeps_rank_one_consistent(self):
        self.needs_revision_20()
        code, result = self.revision([{'idea_id': 'idea-011', 'path': 'working_title', 'value': 'Unique revised title'},
                                      {'path': 'overview.recommended_candidate_ids', 'value': ['idea-009']}])
        self.assertEqual('ready_for_core', result['status'], result)
        self.assertEqual('idea-009', result['rank_adjustment']['idea_id'])
        self.assertEqual('ok', self.stage(self.root, 'core')[1]['status'])
        self.assertEqual('idea-009', self.export()[1]['items'][0]['idea_id'])

    def test_revise_requires_open_core_revision(self):
        self.run_batches(20)
        self.assertEqual(1, self.revision([{'path': 'overview.headline', 'value': 'x'}])[0])


if __name__ == '__main__':
    unittest.main()
