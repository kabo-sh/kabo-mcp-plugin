#!/usr/bin/env python3
"""Observed posting cadence and already-published topics for a proposed plan built from account results.

A proposed "plan for the next 30 days" follows how often the account actually posts, not a fixed default,
and does not re-propose topics the account already published. This reads only the posts the host passes
in (from an account review or another Skill's output); it fetches nothing and is not a native calendar.
"""
import argparse
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import unicodedata

WINDOW_DAYS = 28
STALE_DAYS = 90
# Long function words that say nothing about a topic (EN, DE, ES, PT, FR, IT).
STOPWORDS = {
    'about', 'after', 'again', 'because', 'before', 'being', 'could', 'every', 'first', 'their', 'there', 'these',
    'thing', 'things', 'those', 'video', 'videos', 'where', 'which', 'while', 'would', 'should', 'really', 'without',
    'warum', 'nicht', 'diese', 'dieser', 'dieses', 'einen', 'einem', 'einer', 'etwas', 'immer', 'jeder', 'heute',
    'wirklich', 'sollte', 'wieso', 'deshalb', 'porque', 'sobre', 'cuando', 'donde', 'tambien', 'quando', 'muito',
    'nunca', 'sempre', 'pourquoi', 'comment', 'toujours', 'perche', 'quello', 'questa', 'questo', 'parte',
}


def day(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[T ].*)?', value):
        raise ValueError(f'{field} must be a date (YYYY-MM-DD or an ISO date-time)')
    return date.fromisoformat(value[:10])


def tokens(text):
    """Distinctive words (accents folded) plus CJK character pairs."""
    folded = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
    words = {w for w in re.findall(r'[^\W\d_]+', folded) if len(w) >= 5 and w not in STOPWORDS and not re.search(r'[\u3400-\u9fff]', w)}
    for run in re.findall(r'[\u3400-\u9fff]+', folded):
        words.update(run[i:i + 2] for i in range(len(run) - 1))
    return words


def similar(a, b):
    return a == b or (len(a) >= 6 and len(b) >= 6 and SequenceMatcher(None, a, b).ratio() >= 0.85)


def overlap(topic, title, common):
    shared = sorted({a for a in tokens(topic) - common for b in tokens(title) - common if similar(a, b)})
    # Two shared distinctive words, or one long specific word (a name, doctrine, product), mark the same topic.
    return shared if len(shared) >= 2 or any(len(word) >= 8 for word in shared) else []


def cadence(posts, as_of):
    dates = sorted(day(p['published_at'], 'published_at') for p in posts)
    dates = [d for d in dates if d <= as_of]
    if not dates or (as_of - dates[-1]).days > STALE_DAYS or len(dates) < 2:
        return {'status': 'unknown', 'reason': 'fewer than two dated posts, or none in the last 90 days'}
    # The full days before today: the last four weeks, or the account's whole history when it is younger.
    span = max(7, min(WINDOW_DAYS, (as_of - dates[0]).days))
    count = sum(1 for d in dates if as_of - timedelta(days=span) <= d < as_of)
    per_week = round(count * 7 / span, 1)
    return {'status': 'observed', 'posts_in_window': count, 'window_days': span, 'window_start': (as_of - timedelta(days=span)).isoformat(),
            'window_end': (as_of - timedelta(days=1)).isoformat(), 'posts_per_week': per_week}


def run(data, plan=None):
    if not isinstance(data, dict) or set(data) - {'as_of', 'posts'} or not isinstance(data.get('posts'), list):
        raise ValueError('posts file needs as_of (the creator\'s today) and posts [{published_at, title}]')
    as_of = day(data.get('as_of'), 'as_of')
    for post in data['posts']:
        if not isinstance(post, dict) or set(post) != {'published_at', 'title'} or not isinstance(post['title'], str):
            raise ValueError('each post needs exactly published_at and title (its caption or topic line)')
    result = {'as_of': as_of.isoformat(), 'published_count': len(data['posts']), 'cadence': cadence(data['posts'], as_of)}
    if plan is not None:
        if not isinstance(plan, dict) or set(plan) != {'days', 'topics'} or type(plan['days']) is not int or not 1 <= plan['days'] <= 91 \
                or not isinstance(plan['topics'], list) or not all(isinstance(t, str) and t.strip() for t in plan['topics']):
            raise ValueError('plan needs days (1-91) and topics (one line per proposed post)')
        titles = [p['title'] for p in data['posts']]
        counts = {}
        for title in titles:
            for word in tokens(title):
                counts[word] = counts.get(word, 0) + 1
        # A word in over a quarter of the account's posts is its niche, not a topic (a theology account says "christ").
        common = {w for w, n in counts.items() if n > max(2, len(titles) // 4)}
        duplicates = []
        for index, topic in enumerate(plan['topics']):
            hits = [{'title': title, 'shared': shared} for title in titles if (shared := overlap(topic, title, common))]
            if hits:
                duplicates.append({'index': index, 'topic': topic, 'published': hits[:3]})
        observed = result['cadence']
        expected = round(observed['posts_per_week'] * plan['days'] / 7) if observed['status'] == 'observed' else None
        result.update(plan_days=plan['days'], planned_posts=len(plan['topics']), expected_posts=expected, possible_duplicates=duplicates)
    if result['cadence']['status'] == 'unknown':
        result['next_action'] = 'The account\'s posting frequency is unknown: ask the creator once how often they post, or label the cadence you use as an assumption.'
    elif plan is not None and result['possible_duplicates']:
        result['next_action'] = 'Replace each possible duplicate with a topic the account has not published, unless the creator asked for a follow-up to it; then check again.'
    elif plan is not None and abs(len(plan['topics']) - result['expected_posts']) > max(1, result['expected_posts'] // 5):
        result['next_action'] = (f"The account posts about {result['cadence']['posts_per_week']} times a week, so {plan['days']} days hold about "
                                 f"{result['expected_posts']} posts, not {len(plan['topics'])}. Match that, or state why the plan differs.")
    else:
        result['next_action'] = 'Use this cadence and say it comes from the account\'s own posting history.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--posts', type=Path, required=True)
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding='utf-8')) if args.plan else None
        result = run(json.loads(args.posts.read_text(encoding='utf-8')), plan)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
