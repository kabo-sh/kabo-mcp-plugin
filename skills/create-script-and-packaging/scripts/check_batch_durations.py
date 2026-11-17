#!/usr/bin/env python3
"""Estimate the spoken length of every script in a multi-script request against the requested duration.

A request such as "a 2:30 script for every day from the 16th to the 30th" is only met when each script
is long enough and every requested script is delivered. This uses the same disclosed planning rates as
script_duration.py; it is a heuristic, not a measured read-through.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from script_duration import estimate  # noqa: E402

# A draft within this margin of the requested range reads as that length once paced; outside it, it does not.
SHORT_MARGIN = 0.9
LONG_MARGIN = 1.15


def target_range(value):
    """Accept {"min": s, "max": s} or one number of seconds."""
    if type(value) in (int, float):
        value = {'min': value, 'max': value}
    if not isinstance(value, dict) or set(value) != {'min', 'max'}:
        raise ValueError('target_seconds must be seconds or {"min": seconds, "max": seconds}')
    low, high = value['min'], value['max']
    if type(low) not in (int, float) or type(high) not in (int, float) or not 5 <= low <= high <= 7200:
        raise ValueError('target_seconds must satisfy 5 <= min <= max <= 7200')
    return low, high


def check(batch):
    if not isinstance(batch, dict) or not {'target_seconds', 'requested_count', 'scripts'} <= set(batch) <= {'target_seconds', 'requested_count', 'scripts', 'pace'}:
        raise ValueError('batch needs target_seconds, requested_count and scripts (pace optional)')
    low, high = target_range(batch['target_seconds'])
    requested = batch['requested_count']
    if type(requested) is not int or not 1 <= requested <= 100:
        raise ValueError('requested_count must be the number of scripts the creator asked for (1-100)')
    pace = batch.get('pace', 'normal')
    scripts = batch['scripts']
    if not isinstance(scripts, list) or not scripts:
        raise ValueError('scripts must list every script written so far')
    rows, ids = [], set()
    for item in scripts:
        if not isinstance(item, dict) or set(item) != {'id', 'language', 'spoken_text'}:
            raise ValueError('each script needs exactly id, language and spoken_text (only the words that will be spoken)')
        if not isinstance(item['id'], str) or not item['id'].strip() or item['id'] in ids:
            raise ValueError('script ids must be distinct nonblank strings')
        if not isinstance(item['spoken_text'], str) or not item['spoken_text'].strip():
            raise ValueError(f"script {item['id']}: spoken_text is empty")
        ids.add(item['id'])
        result = estimate({'script': {'language': item['language'], 'scenes': [{'order': 1, 'spoken_text': item['spoken_text']}],
                                      'timing': {'pace': pace, 'non_speaking_segments': []}}, 'hook_options': []})
        seconds = result['estimated_seconds']
        verdict = 'short' if seconds < low * SHORT_MARGIN else 'long' if seconds > high * LONG_MARGIN else 'fits'
        row = {'id': item['id'], 'estimated_seconds': seconds, 'verdict': verdict,
               'word_count': result['word_count'], 'cjk_characters': result['cjk_characters'], 'language_characters': result['language_characters']}
        if verdict == 'short' and seconds > 0:
            # Scale the current copy to the lower bound: how much more spoken copy the script needs.
            row['needs_about_percent_more'] = round((low / seconds - 1) * 100)
        rows.append(row)
    short = [r['id'] for r in rows if r['verdict'] == 'short']
    long = [r['id'] for r in rows if r['verdict'] == 'long']
    missing = max(0, requested - len(rows))
    met = not short and not long and not missing
    if met:
        status, action = 'meets_request', 'Every requested script fits the requested duration; you may say so.'
    elif short or long:
        status = 'needs_revision'
        action = ('Extend the short scripts with real content (another example, step or payoff, never filler) and tighten the long '
                  'ones, then run this check again. If they cannot all be written at full length in this reply, deliver the ones '
                  'that fit now and say plainly how many remain and that they follow next. Never say the scripts meet the duration.')
    else:
        status = 'partial_batch'
        action = (f'{len(rows)} of {requested} scripts are written and fit. Deliver them, say that {missing} are still to come and '
                  'continue with the next batch; never present this batch as the complete set.')
    return {'status': status, 'requested_count': requested, 'checked_count': len(rows), 'missing_count': missing,
            'target_seconds': {'min': low, 'max': high}, 'pace': pace, 'short': short, 'long': long, 'scripts': rows,
            'method': 'heuristic_not_measured_readthrough', 'next_action': action}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.batch.read_text(encoding='utf-8')))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result['status'] == 'meets_request' else 2


if __name__ == '__main__':
    sys.exit(main())
