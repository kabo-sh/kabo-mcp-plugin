#!/usr/bin/env python3
"""Prepare, validate and export a thumbnail review; never call a model or a checker."""
import argparse
import hashlib
import html
import itertools
import json
import os
from pathlib import Path
import re
import sys
import tempfile

sys.dont_write_bytecode = True
RUBRIC = json.loads((Path(__file__).resolve().parent.parent / 'references/rubric.json').read_text())
ITEMS = RUBRIC['items']
CONTEXT = {'title', 'video_url', 'video_summary', 'source_reference', 'channel_reference', 'peer_reference', 'source_disclosure', 'audience', 'target_aspect_ratio'}
FINAL = ('FINAL_REVIEW.md', 'delivery.json')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'Duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def write(path, value):
    data = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
            name = f.name
            f.write(data)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected), 'Unexpected or missing object fields: ' + ','.join(expected))


def sentence(value):
    require(isinstance(value, str) and 0 < len(value.strip()) <= 600 and '\n' not in value, 'Expected one nonblank reason, at most 600 characters')


def safe_file(run, relative):
    require(isinstance(relative, str), 'Expected a relative file path')
    p = (run / relative).resolve()
    require(p.is_relative_to(run.resolve()) and p.is_file() and not (run / relative).is_symlink(), 'Invalid run file')
    return p


def check_ratio(context):
    value = context.get('target_aspect_ratio')
    if value is not None:
        require(bool(re.fullmatch(r'[1-9][0-9]{0,3}:[1-9][0-9]{0,3}', value)), 'Use an explicit target ratio such as 16:9 or 9:16')


def prepare(source, run):
    from PIL import Image, ImageOps
    request = load(source)
    keys(request, ('images', 'context', 'language'))
    require(request['language'] in ('en', 'zh'), 'language must be en or zh')
    require(isinstance(request['context'], dict) and set(request['context']) <= CONTEXT, 'Unknown context fields')
    for value in request['context'].values():
        require(isinstance(value, str) and 0 < len(value.strip()) <= 12000, 'Context must contain nonblank evidence text')
    check_ratio(request['context'])
    require(isinstance(request['images'], list) and 1 <= len(request['images']) <= 3, 'Upload 1 to 3 images')
    require(not run.exists(), 'Use a new run directory; never overwrite an earlier review')
    # 先验证全部输入，再创建运行目录；保留失败目录，不重用旧成功回执。
    sources = []
    for value in request['images']:
        require(isinstance(value, str), 'Image paths must be strings')
        path = (source.parent / value).resolve()
        with Image.open(path) as im:
            require(im.format in ('PNG', 'JPEG', 'WEBP') and getattr(im, 'n_frames', 1) == 1, 'Use static PNG, JPEG or WebP')
            require(0 < im.width * im.height <= 40000000, 'Image exceeds 40 megapixels')
            im.load()
        sources.append(path)
    require(len({digest(p.read_bytes()) for p in sources}) == len(sources), 'Duplicate image bytes are not separate candidates')
    run.mkdir(parents=True)
    records = []
    for ident, source_path in zip('ABC', sources):
        original = f'{ident}.source{source_path.suffix.lower()}'
        (run / original).write_bytes(source_path.read_bytes())
        with Image.open(source_path) as im:
            im = ImageOps.exif_transpose(im).convert('RGBA')
            width, height = im.size
            thumb = im.copy()
            thumb.thumbnail((320, 320), Image.Resampling.LANCZOS)
            thumb.save(run / f'{ident}.small.png')
        records.append({'id': ident, 'path': original, 'sha256': digest((run / original).read_bytes()),
                        'small_path': f'{ident}.small.png', 'small_sha256': digest((run / f'{ident}.small.png').read_bytes()),
                        'width': width, 'height': height})
    request['images'] = records
    request['schema_version'] = 'review-thumbnail.request.v2'
    write(run / 'request.json', request)
    return {'status': 'prepared', 'run_dir': str(run.resolve()), 'next': 'Inspect all originals and small images, then author review.json. Preparation is not a review.'}


def inputs(run):
    request = load(run / 'request.json')
    keys(request, ('schema_version', 'images', 'context', 'language'))
    require(request['schema_version'] == 'review-thumbnail.request.v2', 'Wrong request version')
    require(request['language'] in ('en', 'zh'), 'Unsupported language')
    require(isinstance(request['context'], dict) and set(request['context']) <= CONTEXT, 'Unknown context')
    for value in request['context'].values():
        require(isinstance(value, str) and 0 < len(value.strip()) <= 12000, 'Invalid context')
    check_ratio(request['context'])
    require(isinstance(request['images'], list) and 1 <= len(request['images']) <= 3, 'Expected 1 to 3 images')
    for n, r in enumerate(request['images']):
        keys(r, ('id', 'path', 'sha256', 'small_path', 'small_sha256', 'width', 'height'))
        require(r['id'] == 'ABC'[n], 'Stable candidate IDs must be A/B/C')
        from PIL import Image, ImageOps
        with Image.open(safe_file(run, r['path'])) as im:
            im = ImageOps.exif_transpose(im)
            require(type(r['width']) is int and type(r['height']) is int and im.size == (r['width'], r['height']), 'Image dimensions changed')
        for file_key, hash_key in [('path', 'sha256'), ('small_path', 'small_sha256')]:
            require(digest(safe_file(run, r[file_key]).read_bytes()) == r[hash_key], 'Image bytes changed after preparation')
    return request


def validate(run):
    request = inputs(run)
    review = load(run / 'review.json')
    keys(review, ('schema_version', 'request_sha256', 'candidates', 'comparisons', 'recommendation'))
    require(review['schema_version'] == 'review-thumbnail.review.v2', 'Wrong review version')
    require(review['request_sha256'] == digest((run / 'request.json').read_bytes()), 'Review is bound to different inputs')
    ids = [r['id'] for r in request['images']]
    require(isinstance(review['candidates'], list) and all(isinstance(c, dict) for c in review['candidates']) and [c.get('id') for c in review['candidates']] == ids, 'Missing, duplicate or reordered candidates')
    outcomes = {}
    for candidate in review['candidates']:
        keys(candidate, ('id', 'items', 'priorities', 'suitable', 'suitability_reason'))
        rows = candidate['items']
        require(isinstance(rows, dict) and set(rows) == {i['id'] for i in ITEMS}, 'All ten rubric items are required exactly once')
        for item in ITEMS:
            row = rows[item['id']]
            keys(row, ('verdict', 'reason', 'fix', 'basis'))
            sentence(row['reason'])
            require(row['verdict'] in ('pass', 'fail'), 'Use only pass or fail; no scores or third verdict')
            require(row['basis'] in ('observed', 'missing_context'), 'Invalid evidence basis')
            if row['verdict'] == 'fail':
                sentence(row['fix'])
            else:
                require(row['fix'] == '' and row['basis'] == 'observed', 'Pass must have observed support and no invented fix')
            if item['id'] == 'topic_match' and not any(request['context'].get(k) for k in ('title', 'video_summary', 'source_reference')):
                require(row['verdict'] == 'fail' and row['basis'] == 'missing_context', 'Video URL alone cannot prove topic match')
            if item['id'] == 'resolution_aspect' and not request['context'].get('target_aspect_ratio'):
                require(row['verdict'] == 'fail' and row['basis'] == 'missing_context', 'Target aspect ratio is required to verify format')
        failed = {k for k, v in rows.items() if v['verdict'] == 'fail'}
        priorities = candidate['priorities']
        require(isinstance(priorities, list) and all(isinstance(v, str) for v in priorities), 'Priority IDs must be strings')
        require(len(set(priorities)) == len(priorities) and set(priorities) <= failed, 'Priorities must be distinct failed items')
        require(min(2, len(failed)) <= len(priorities) <= min(3, len(failed)), 'Pick the first 2–3 fixes; fewer only when fewer items failed')
        require(type(candidate['suitable']) is bool, 'Suitability must be a boolean editorial judgment')
        sentence(candidate['suitability_reason'])
        require(not candidate['suitable'] or len(failed) < len(ITEMS), 'An all-fail candidate cannot be suitable')
        require(not candidate['suitable'] or all(r['basis'] != 'missing_context' for r in rows.values()), 'Missing context cannot establish suitability')
        if request['context'].get('target_aspect_ratio'):
            w, h = map(int, request['context']['target_aspect_ratio'].split(':'))
            image = request['images'][ids.index(candidate['id'])]
            if abs(image['width'] / image['height'] / (w / h) - 1) > 0.01:
                require(rows['resolution_aspect']['verdict'] == 'fail', 'Actual aspect ratio differs from target')
        outcomes[candidate['id']] = {'suitable': candidate['suitable'], 'failed_items': [i['id'] for i in ITEMS if i['id'] in failed]}
    pairs = list(itertools.combinations(ids, 2))
    require(isinstance(review['comparisons'], list) and len(review['comparisons']) == len(pairs), 'Compare every pair exactly once')
    for row, pair in zip(review['comparisons'], pairs):
        keys(row, ('pair', 'winner', 'reason'))
        require(row['pair'] == list(pair) and row['winner'] in (*pair, 'tie', 'neither', 'insufficient'), 'Invalid pair or winner')
        sentence(row['reason'])
        eligible = [i for i in pair if outcomes[i]['suitable']]
        require(row['winner'] not in pair or row['winner'] in eligible, 'Cannot prefer an unsuitable image')
        require(row['winner'] != 'tie' or len(eligible) == 2, 'Tie requires two suitable candidates')
        require(eligible or row['winner'] == 'neither', 'Both unsuitable: use neither')
    rec = review['recommendation']
    keys(rec, ('candidate_id', 'reason'))
    sentence(rec['reason'])
    require(rec['candidate_id'] is None or rec['candidate_id'] in ids, 'Unknown recommendation')
    if rec['candidate_id']:
        require(outcomes[rec['candidate_id']]['suitable'], 'Unsuitable candidates cannot be recommended')
        require(all(p['winner'] in (rec['candidate_id'], 'tie') for p in review['comparisons'] if rec['candidate_id'] in p['pair']), 'Recommendation contradicts a pairwise result')
    return request, review, outcomes


def text(value):
    # 所有模型与上传文字均转义，禁止原文注入HTML、Markdown链接或额外表格行。
    return html.escape(str(value), quote=False).replace('\\', '&#92;').replace('|', '&#124;').replace('[', '&#91;').replace(']', '&#93;').replace('*', '&#42;').replace('`', '&#96;').replace('\n', ' ')


def render(request, review, outcomes):
    zh = request['language'] == 'zh'
    labels = json.loads((Path(__file__).resolve().parent.parent / 'references/labels-zh.json').read_text()) if zh else {}
    label = lambda ident, fallback: labels.get(ident, fallback)
    names = {i['id']: label(i['id'], i['label']) for i in ITEMS}
    lines = ['# ' + ('封面评测' if zh else 'Thumbnail review'), '',
             'AI编辑建议，不代表实际点击率。缺依据的“不过”会说明需补充什么。' if zh else 'AI editorial advice, not measured CTR. Evidence gaps appear as failed checks with a request for the missing context.', '']
    for c in review['candidates']:
        lines += ['## ' + c['id'], '', text(c['suitability_reason']), '',
                  '| 项目 | 判断 | 一句理由 | 怎么改 |' if zh else '| Item | Verdict | Reason | How to improve |', '|---|---|---|---|']
        for item in ITEMS:
            r = c['items'][item['id']]
            lines.append(f"| {names[item['id']]} | {label(r['verdict'], r['verdict'])} | {text(r['reason'])} | {text(r['fix']) if r['fix'] else '—'} |")
        lines += ['', '### ' + ('最先要改' if zh else 'Change first'), '']
        if not c['priorities']:
            lines.append('没有必须修改的项。' if zh else 'No required changes identified.')
        for n, ident in enumerate(c['priorities'], 1):
            lines.append(f"{n}. {names[ident]} — {text(c['items'][ident]['fix'])}")
        lines.append('')
    if review['comparisons']:
        lines += ['## ' + ('放在一起比' if zh else 'Compare the candidates'), '']
        for p in review['comparisons']:
            lines.append(f"- {' / '.join(p['pair'])}: {label(p['winner'], p['winner'])} — {text(p['reason'])}")
        lines.append('')
    all_failed = all(not o['suitable'] for o in outcomes.values())
    decision = ('都不理想，暂不推荐。' if zh else 'None is suitable; no recommendation yet.') if all_failed else (review['recommendation']['candidate_id'] or ('暂无明确推荐' if zh else 'No clear recommendation'))
    lines += ['## ' + ('推荐' if zh else 'Recommendation'), '', decision, '', text(review['recommendation']['reason']), '']
    return '\n'.join(lines)


def deliver(run):
    for name in FINAL:
        (run / name).unlink(missing_ok=True)
    request, review, outcomes = validate(run)
    report = render(request, review, outcomes)
    receipt = {'schema_version': 'review-thumbnail.delivery.v2', 'status': 'validated', 'report_path': str((run / FINAL[0]).resolve()),
               'report_sha256': digest(report.encode()), 'inputs': {n: digest((run / n).read_bytes()) for n in ('request.json', 'review.json')},
               'outcomes': outcomes, 'next_action': 'Display the unchanged file with emit_block: {"block":{"type":"markdown","path":report_path}}. Verify emission before claiming delivery.'}
    try:
        write(run / FINAL[0], report)
        write(run / FINAL[1], receipt)
    except OSError:
        for name in FINAL:
            (run / name).unlink(missing_ok=True)
        raise
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'validate', 'deliver'))
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            require(args.input is not None, '--input is required')
        if args.command == 'prepare':
            result = prepare(args.input.resolve(), args.run_dir.resolve())
        elif args.command == 'validate':
            result = {'status': 'validated', 'outcomes': validate(args.run_dir.resolve())[2]}
        else:
            result = deliver(args.run_dir.resolve())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(json.dumps({'status': 'not_deliverable', 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
