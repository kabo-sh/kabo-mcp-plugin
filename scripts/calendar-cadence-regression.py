#!/usr/bin/env python3
"""9abe9929 shape: after an account review, "a concrete TikTok plan for the next 30 days" defaulted to three posts a
week for an account that posts almost daily, and re-proposed topics the account had already published."""
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/plan-content-calendar/scripts/account_cadence.py'
PUBLISHED = [
    'Ich glaube an Sola Skriptura – und das heißt nicht, dass Tradition egal ist',
    'Warum ich als Christ kein Fast Food mehr esse',
    'Etwas, was jeder Christ wissen sollte: wie die Evangelien eigentlich entstanden sind',
    'Glaube im Gym: mein Gedankengang als Christ',
    'Dürfen LGBTQ-Menschen in die Kirche? Meine Antwort als Christ',
    'Reaktion: Ist Jesus nur ein Prophet? Ein Christ antwortet',
]


def posts(count=28, every=1):
    today = date(2026, 11, 12)
    rows = [{'published_at': (today - timedelta(days=1 + n * every)).isoformat(), 'title': PUBLISHED[n % len(PUBLISHED)] + f' #{n}'} for n in range(count)]
    return {'as_of': today.isoformat(), 'posts': rows}


class Cadence(unittest.TestCase):
    def check(self, data, plan=None):
        with tempfile.TemporaryDirectory() as temp:
            args = [sys.executable, '-B', str(SCRIPT), '--posts', str(Path(temp) / 'posts.json')]
            (Path(temp) / 'posts.json').write_text(json.dumps(data, ensure_ascii=False))
            if plan is not None:
                (Path(temp) / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False))
                args += ['--plan', str(Path(temp) / 'plan.json')]
            result = subprocess.run(args, capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_daily_account_does_not_get_three_posts_a_week(self):
        draft = {'days': 30, 'topics': [f'Neues Thema {n}: Trinität und Analogie {n}' for n in range(12)]}
        code, result = self.check(posts(), draft)
        self.assertEqual(0, code, result)
        self.assertEqual('observed', result['cadence']['status'])
        self.assertEqual(7.0, result['cadence']['posts_per_week'])
        self.assertEqual(30, result['expected_posts'])
        self.assertIn('not 12', result['next_action'])

    def test_already_published_topics_are_flagged(self):
        draft = {'days': 30, 'topics': ['Die Trinität bedeutet nicht drei Götter', 'Was Sola Scriptura wirklich bedeutet',
                                        'Wie die Evangelien entstanden sind – kurz erklärt', 'Warum Jesus beim Gebet zu Gott betet']}
        _, result = self.check(posts(), draft)
        flagged = [row['topic'] for row in result['possible_duplicates']]
        self.assertEqual(['Was Sola Scriptura wirklich bedeutet', 'Wie die Evangelien entstanden sind – kurz erklärt'], flagged)
        self.assertIn('Replace each possible duplicate', result['next_action'])

    def test_niche_words_alone_are_not_duplicates(self):
        # "Christ" is in most of this account's posts: it is the niche, not a repeated topic.
        draft = {'days': 7, 'topics': ['Was ein Christ über Schulden wissen sollte']}
        _, result = self.check(posts(), draft)
        self.assertEqual([], result['possible_duplicates'])

    def test_matching_plan_passes(self):
        draft = {'days': 14, 'topics': [f'Thema {n}: Bibelstelle Kontext {n}' for n in range(14)]}
        _, result = self.check(posts(), draft)
        self.assertEqual(14, result['expected_posts'])
        self.assertIn('posting history', result['next_action'])

    def test_weekly_account(self):
        _, result = self.check(posts(count=10, every=7))
        self.assertEqual(1.0, result['cadence']['posts_per_week'])

    def test_unknown_cadence_asks_once(self):
        _, result = self.check({'as_of': '2026-11-12', 'posts': [{'published_at': '2026-01-01', 'title': 'Alt'}]}, {'days': 30, 'topics': ['a']})
        self.assertEqual('unknown', result['cadence']['status'])
        self.assertIn('ask the creator once', result['next_action'])

    def test_invalid_input(self):
        code, result = self.check({'posts': [{'title': 'x'}]})
        self.assertEqual((1, 'invalid_input'), (code, result['status']))

    def test_skill_routes_account_plans_through_the_check(self):
        skill = (ROOT / 'skills/plan-content-calendar/SKILL.md').read_text()
        self.assertIn('account_cadence.py', skill)
        self.assertIn('Never invent a fixed default cadence for a known account', skill)


if __name__ == '__main__':
    unittest.main()
