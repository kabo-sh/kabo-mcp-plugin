#!/usr/bin/env python3
"""S056 shape: fifteen daily Shorts of 2:20-2:30 written at about 180 words each were delivered as meeting the length."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/create-script-and-packaging/scripts/check_batch_durations.py'
WORDS = 'la mente tranquila aprende a soltar lo que no puede controlar y vuelve a respirar despacio'.split()


def spoken(count):
    return ' '.join(WORDS[i % len(WORDS)] for i in range(count)) + '.'


class BatchDurations(unittest.TestCase):
    def run_check(self, batch):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'batch.json'
            path.write_text(json.dumps(batch, ensure_ascii=False))
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--batch', str(path)], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def batch(self, words, count=15, requested=15, pace='deliberate'):
        return {'target_seconds': {'min': 140, 'max': 150}, 'requested_count': requested, 'pace': pace,
                'scripts': [{'id': f'Nov {16 + n}', 'language': 'es', 'spoken_text': spoken(words)} for n in range(count)]}

    def test_fifteen_short_scripts_cannot_be_called_two_and_a_half_minutes(self):
        code, result = self.run_check(self.batch(180))
        self.assertEqual((2, 'needs_revision'), (code, result['status']))
        self.assertEqual(15, len(result['short']))
        self.assertLess(result['scripts'][0]['estimated_seconds'], 100)
        self.assertGreater(result['scripts'][0]['needs_about_percent_more'], 50)
        self.assertIn('Never say the scripts meet the duration', result['next_action'])

    def test_full_length_scripts_meet_the_request(self):
        code, result = self.run_check(self.batch(330))
        self.assertEqual((0, 'meets_request'), (code, result['status']), result)
        code, result = self.run_check(self.batch(380, pace='normal'))
        self.assertEqual((0, 'meets_request'), (code, result['status']), result)

    def test_a_first_batch_is_not_the_complete_set(self):
        code, result = self.run_check(self.batch(330, count=5))
        self.assertEqual((2, 'partial_batch', 10), (code, result['status'], result['missing_count']))
        self.assertIn('10 are still to come', result['next_action'])

    def test_overlong_scripts_are_flagged(self):
        code, result = self.run_check(self.batch(450))
        self.assertEqual('needs_revision', result['status'])
        self.assertEqual(15, len(result['long']))

    def test_chinese_scripts_use_character_rates(self):
        batch = {'target_seconds': 60, 'requested_count': 1,
                 'scripts': [{'id': 'a', 'language': 'zh-CN', 'spoken_text': '慢慢呼吸' * 60}]}
        self.assertEqual('meets_request', self.run_check(batch)[1]['status'])

    def test_invalid_input(self):
        code, result = self.run_check({'target_seconds': 150, 'scripts': []})
        self.assertEqual((1, 'invalid_input'), (code, result['status']))

    def test_skill_requires_the_check_before_claiming_length(self):
        skill = (ROOT / 'skills/create-script-and-packaging/SKILL.md').read_text()
        self.assertIn('check_batch_durations.py', skill)
        self.assertIn('meets_request', skill)


if __name__ == '__main__':
    unittest.main()
