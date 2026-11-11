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


if __name__ == '__main__':
    unittest.main()
