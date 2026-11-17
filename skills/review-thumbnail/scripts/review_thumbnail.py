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
REFERENCES = Path(__file__).resolve().parent.parent / 'references'
RUBRIC = json.loads((REFERENCES / 'rubric.json').read_text())
ITEMS = RUBRIC['items']
# Fixed report labels by catalog. Any other language supplies its own complete `labels` in request-input.json.
CATALOGS = json.loads((REFERENCES / 'labels.json').read_text(encoding='utf-8'))
LABEL_KEYS = frozenset(CATALOGS['en'])
CONTEXT = {'title', 'video_url', 'video_summary', 'source_reference', 'channel_reference', 'peer_reference', 'source_disclosure', 'audience', 'target_aspect_ratio', 'target_aspect_source'}
ASPECT_SOURCES = ('user', 'format')
FINAL = ('FINAL_REVIEW.md', 'delivery.json')
REQUEST_VERSION = 'review-thumbnail.request.v3'
REVIEW_VERSION = 'review-thumbnail.review.v3'
# Ratio tolerance: covers pixel rounding (2752x1536 is 0.78% from 16:9 and passes); it is not a quality score.
TOLERANCE = 0.01
# Common thumbnail and cover ratios. A size far from all of them (749x407, 740x443) is a screenshot or crop.
STANDARD_RATIOS = ((16, 9), (9, 16), (4, 5), (1, 1), (4, 3), (3, 4), (2, 3), (3, 2), (5, 4))
STANDARD_TOLERANCE = 0.02
# Title length: YouTube rejects titles over 100 characters; lists show roughly 70 display columns.
TITLE_MAX_CHARS = 100
TITLE_SHOWN_COLUMNS = 70


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


def keys(value, expected, where='object'):
    """Name the object and the exact missing or unexpected fields, so one correction is enough."""
    if not isinstance(value, dict):
        raise ValueError(f'{where} must be an object with exactly these fields: {", ".join(expected)} (see review_template from prepare)')
    missing, extra = [k for k in expected if k not in value], sorted(set(value) - set(expected))
    require(not missing and not extra, f'{where}: missing fields {missing}, unexpected fields {extra}; '
            f'it needs exactly {", ".join(expected)} (see review_template from prepare)')


def sentence(value):
    require(isinstance(value, str) and 0 < len(value.strip()) <= 600 and '\n' not in value, 'Expected one nonblank reason, at most 600 characters')


# Quoted text must be text actually seen on that candidate, so another image's headline cannot be attributed to it.
QUOTE = re.compile(r'[“"「『«]([^”"」』»]{2,80})[”"」』»]')
# Source labels and disclaimers required by a platform or regulation are not clutter: never ask to remove or hide them.
# The non-English alternatives match removal requests written in a Chinese, Portuguese or Spanish review.
REMOVAL = re.compile(r'(删除|删掉|去掉|去除|移除|拿掉|隐藏|遮住|淡化到看不见|remov|delet|drop|hide|erase|get rid of|retir|apag|ocult|elimin|quit)', re.I)
# Ratio notation and percentages belong to the script's measurement, never to a model-written resolution_aspect row.
RATIO_CLAIM = re.compile(r'\d+(?:[.,]\d+)?\s*:\s*\d+|\d+(?:[.,]\d+)?\s*%')


def norm(value):
    return re.sub(r'\s+', ' ', value).strip().casefold()


def text_list(value, field, limit=200):
    require(isinstance(value, list) and all(isinstance(t, str) and t.strip() and len(t) <= limit for t in value),
            f'{field} must list each text exactly as seen (empty list if none)')
    return value


def observations(value):
    keys(value, ('capture', 'visible_text', 'ui_text', 'main_subject', 'disclosures'), 'observations')
    require(value['capture'] in ('original', 'screenshot'),
            'capture must be "original" (the cover image itself) or "screenshot" (a capture that shows platform interface '
            'such as a duration badge, video title, channel name or view count around or over the cover)')
    text_list(value['visible_text'], 'visible_text')
    # Platform interface text in a screenshot is not cover text: keep it apart so it is never judged as the cover's words.
    text_list(value['ui_text'], 'ui_text')
    require(value['capture'] == 'screenshot' or not value['ui_text'], 'ui_text is only for a screenshot; an original cover has no platform interface')
    # The same words may be on the cover and in the interface (an artist name on the cover and in the list title):
    # list them in both. Only text that is on the cover itself belongs in visible_text.
    text_list(value['disclosures'], 'disclosures')
    sentence(value['main_subject'])
    seen = ' | '.join(norm(t) for t in value['visible_text'])
    for label in value['disclosures']:
        require(norm(label) in seen, 'Each disclosure must also appear in visible_text: ' + label)
    return seen


def grounded(textvalue, seen, where, ui=()):
    for quoted in QUOTE.findall(textvalue):
        if norm(quoted) in seen:
            continue
        require(not any(norm(quoted) in norm(item) for item in ui),
                f'{where} quotes platform interface text ({quoted}); interface text in a screenshot is not part of the cover')
        raise ValueError(f'{where} quotes text not recorded in visible_text: {quoted}')


def keeps_disclosures(textvalue, disclosures, where):
    low = norm(textvalue)
    for label in disclosures:
        if norm(label) in low and REMOVAL.search(textvalue):
            raise ValueError(f'{where} asks to remove a required disclosure ({label}); disclosures must stay readable')


def safe_file(run, relative):
    require(isinstance(relative, str), 'Expected a relative file path')
    p = (run / relative).resolve()
    require(p.is_relative_to(run.resolve()) and p.is_file() and not (run / relative).is_symlink(), 'Invalid run file')
    return p


def check_ratio(context):
    value = context.get('target_aspect_ratio')
    if value is not None:
        require(bool(re.fullmatch(r'[1-9][0-9]{0,3}:[1-9][0-9]{0,3}', value)), 'Use an explicit target ratio such as 16:9 or 9:16')
        # Say where the ratio came from, so the report never claims the creator asked for a ratio they did not name.
        require(context.get('target_aspect_source') in ASPECT_SOURCES,
                'target_aspect_source must be "user" (the creator named this ratio or size) or "format" (the creator named a '
                'format whose standard ratio this is, such as a YouTube long-form video); otherwise omit target_aspect_ratio')
    else:
        require('target_aspect_source' not in context, 'target_aspect_source needs target_aspect_ratio')


def catalog_key(language):
    """Map a BCP 47 tag to a built-in label catalog, or None when the request must supply labels."""
    require(isinstance(language, str) and bool(re.fullmatch(r'[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*', language)),
            'language must be a BCP 47 tag of the creator\'s language, such as pt-BR, zh-TW or tr')
    parts = language.lower().replace('_', '-').split('-')
    if parts[0] == 'zh':
        return 'zh-Hant' if {'hant', 'tw', 'hk', 'mo'} & set(parts[1:]) else 'zh'
    return parts[0] if parts[0] in CATALOGS else None


def placeholders(value):
    return sorted(re.findall(r'\{[a-z_]+\}', value))


def check_labels(request):
    """Built-in languages use their catalog; any other language must bring a complete translation, never English."""
    key = catalog_key(request['language'])
    labels = request.get('labels')
    if key is not None:
        require(labels is None, f'language {request["language"]} has built-in labels; omit labels')
        return CATALOGS[key]
    require(isinstance(labels, dict), f'language {request["language"]} has no built-in labels: add "labels" with every key of '
            'the English catalog in references/labels.json translated into that language; never fall back to English')
    missing, extra = sorted(LABEL_KEYS - set(labels)), sorted(set(labels) - LABEL_KEYS)
    require(not missing and not extra, f'labels must have exactly the English catalog keys; missing {missing}, unknown {extra}')
    for name, value in labels.items():
        require(isinstance(value, str) and value.strip() and '\n' not in value and len(value) <= 400, f'labels.{name} must be one nonblank line')
        require(placeholders(value) == placeholders(CATALOGS['en'][name]), f'labels.{name} must keep the placeholders {placeholders(CATALOGS["en"][name])}')
    english = [i['id'] for i in ITEMS if labels[i['id']].strip().casefold() == CATALOGS['en'][i['id']].casefold()]
    require(len(english) <= 3, f'labels are still English for {english}; translate them into {request["language"]}')
    # Authored labels are model text: escape them like every other model string in the report.
    return {name: text(value) for name, value in labels.items()}


def standard_size(width, height):
    return any(abs(width / height / (w / h) - 1) <= STANDARD_TOLERANCE for w, h in STANDARD_RATIOS)


def aspect_check(image, context, capture):
    """The script, not the model, decides the ratio part of resolution_aspect."""
    width, height = image['width'], image['height']
    result = {'width': width, 'height': height, 'ratio': round(width / height, 3), 'standard_size': standard_size(width, height)}
    target = context.get('target_aspect_ratio')
    if target:
        w, h = map(int, target.split(':'))
        result.update(target=target, target_ratio=round(w / h, 3), deviation_percent=round(abs(width / height / (w / h) - 1) * 100, 2))
    if capture == 'screenshot':
        status = 'screenshot'
    elif not result['standard_size'] and context.get('target_aspect_source') != 'user':
        status = 'nonstandard_size'
    elif not target:
        status = 'no_target'
    else:
        status = 'pass' if abs(width / height / (w / h) - 1) <= TOLERANCE else 'fail'
    result['status'] = status
    return result


def title_length(title):
    """Count characters and display columns (wide CJK characters take two columns)."""
    import unicodedata
    chars = len(title)
    columns = sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in title)
    status = 'over' if chars > TITLE_MAX_CHARS else 'long' if columns > TITLE_SHOWN_COLUMNS else 'ok'
    return {'chars': chars, 'columns': columns, 'status': status}


def review_template(request, request_sha256):
    """The exact review.json shape for this request, so the first submission has the right fields and nesting."""
    ids = [r['id'] for r in request['images']]
    row = {'verdict': 'pass or fail', 'reason': 'one sentence', 'fix': 'empty for pass; one fix for fail', 'basis': 'observed or missing_context'}
    template = {
        'schema_version': REVIEW_VERSION,
        'request_sha256': request_sha256,
        'candidates': [{
            'id': ident,
            'observations': {'capture': 'original or screenshot', 'visible_text': ['each cover text exactly as written'],
                             'ui_text': ['platform interface text of a screenshot; empty list for an original'],
                             'main_subject': 'one sentence', 'disclosures': []},
            'items': {item['id']: dict(row) for item in ITEMS},
            'priorities': ['failed item ids, first 2-3'],
            'suitable': True,
            'suitability_reason': 'one sentence',
        } for ident in ids],
        'title_review': None,
        'comparisons': [{'pair': list(pair), 'winner': f'{pair[0]}, {pair[1]}, tie, neither or insufficient', 'reason': 'one sentence'}
                        for pair in itertools.combinations(ids, 2)],
        'recommendation': {'candidate_id': f'{" or ".join(ids)} or null', 'reason': 'one sentence'},
    }
    if request['context'].get('title'):
        template['title_review'] = {
            'title': request['context']['title'],
            'clarity': {'verdict': 'pass or fail', 'reason': 'one sentence', 'fix': 'empty for pass'},
            'pairing': [{'candidate_id': ident, 'verdict': 'pass or fail', 'reason': 'one sentence', 'fix': 'empty for pass'} for ident in ids],
        }
    return template


def prepare(source, run):
    from PIL import Image, ImageOps
    request = load(source)
    require(isinstance(request, dict) and {'images', 'context', 'language'} <= set(request) <= {'images', 'context', 'language', 'labels'},
            'request-input.json needs images, context and language, plus labels only for a language without built-in labels')
    check_labels(request)
    require(isinstance(request['context'], dict) and set(request['context']) <= CONTEXT, 'Unknown context fields')
    for value in request['context'].values():
        require(isinstance(value, str) and 0 < len(value.strip()) <= 12000, 'Context must contain nonblank evidence text')
    check_ratio(request['context'])
    require(isinstance(request['images'], list) and 1 <= len(request['images']) <= 3, 'Upload 1 to 3 images')
    # Hosts often create the working folder to hold request-input.json, so name the fix, not just the rule.
    require(not run.exists(), 'Use a new run directory; never overwrite an earlier review. --run-dir must not exist yet: '
            'pass a new subdirectory such as --run-dir review, not "." or the folder holding the input file')
    # Validate every input before creating the run directory; keep failed directories and never reuse an earlier success receipt.
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
    request['schema_version'] = REQUEST_VERSION
    write(run / 'request.json', request)
    template = review_template(request, digest((run / 'request.json').read_bytes()))
    write(run / 'review.template.json', template)
    measured = [{'id': r['id'], **aspect_check(r, request['context'], 'original')} for r in records]
    result = {'status': 'prepared', 'run_dir': str(run.resolve()), 'measurements': measured,
              'next': 'Inspect all originals and small images, then author review.json. Preparation is not a review. '
                      'The ratio verdict is the script\'s: measurements[].status is final for an original image (a screenshot '
                      'you mark with capture "screenshot" is not ratio-checked). Never restate or recompute the ratio or its tolerance. '
                      'Copy review_template (also saved as review.template.json, with request_sha256 already filled) to review.json '
                      'and replace every placeholder; keep its field names and nesting exactly.',
              'review_template': template}
    if request['context'].get('title'):
        result['title_length'] = title_length(request['context']['title'])
        result['next'] += ' A title was given: fill title_review (clarity and how the title pairs with each candidate).'
    return result


def inputs(run):
    request = load(run / 'request.json')
    require(isinstance(request, dict) and {'schema_version', 'images', 'context', 'language'} <= set(request) <= {'schema_version', 'images', 'context', 'language', 'labels'}, 'Unexpected request fields')
    require(request['schema_version'] == REQUEST_VERSION, 'Wrong request version')
    check_labels(request)
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


def verdict_row(row, fields, where, quotable, ui=()):
    keys(row, fields, where)
    sentence(row['reason'])
    grounded(row['reason'], quotable, where + ' reason', ui)
    require(row['verdict'] in ('pass', 'fail'), 'Use only pass or fail; no scores or third verdict')
    if row['verdict'] == 'fail':
        sentence(row['fix'])
    else:
        require(row['fix'] == '', f'{where}: a pass has no fix')


def check_title_review(request, review, ids, seen_by_id, ui_by_id):
    """A supplied title is reviewed with the covers: its clarity and how it pairs with each candidate.

    The length row is measured by the script and is not authored by the model.
    """
    title = request['context'].get('title')
    value = review['title_review']
    if not title:
        require(value is None, 'title_review must be null when the request has no title')
        return None
    require(isinstance(value, dict), 'A title was given: title_review must review it (clarity and pairing with each candidate)')
    keys(value, ('title', 'clarity', 'pairing'), 'title_review')
    require(value['title'] == title, 'title_review.title must be the exact title in the request context')
    title_seen = norm(title)
    verdict_row(value['clarity'], ('verdict', 'reason', 'fix'), 'title_review.clarity', title_seen)
    pairing = value['pairing']
    require(isinstance(pairing, list) and [row.get('candidate_id') if isinstance(row, dict) else None for row in pairing] == ids,
            'title_review.pairing needs one row per candidate, in order A/B/C, each with candidate_id, verdict, reason and fix')
    for row in pairing:
        cid = row['candidate_id']
        verdict_row(row, ('candidate_id', 'verdict', 'reason', 'fix'), f'title_review.pairing {cid}', title_seen + ' | ' + seen_by_id[cid], ui_by_id[cid])
    return title_length(title)


def validate(run):
    request = inputs(run)
    review = load(run / 'review.json')
    keys(review, ('schema_version', 'request_sha256', 'candidates', 'title_review', 'comparisons', 'recommendation'), 'review.json')
    require(review['schema_version'] == REVIEW_VERSION, 'Wrong review version')
    require(review['request_sha256'] == digest((run / 'request.json').read_bytes()), 'Review is bound to different inputs')
    ids = [r['id'] for r in request['images']]
    require(isinstance(review['candidates'], list) and all(isinstance(c, dict) for c in review['candidates']) and [c.get('id') for c in review['candidates']] == ids, 'Missing, duplicate or reordered candidates')
    context = request['context']
    title_seen = norm(context['title']) if context.get('title') else ''
    outcomes, seen_by_id, ui_by_id = {}, {}, {}
    for candidate, image in zip(review['candidates'], request['images']):
        keys(candidate, ('id', 'observations', 'items', 'priorities', 'suitable', 'suitability_reason'), 'candidate ' + str(candidate.get('id')))
        seen = observations(candidate['observations'])
        ui = candidate['observations']['ui_text']
        seen_by_id[candidate['id']], ui_by_id[candidate['id']] = seen, ui
        # The title may be quoted where the cover is judged against it; platform interface text may not.
        quotable = seen + (' | ' + title_seen if title_seen else '')
        disclosures = candidate['observations']['disclosures']
        grounded(candidate['suitability_reason'], quotable, candidate['id'] + ' suitability', ui)
        aspect = aspect_check(image, context, candidate['observations']['capture'])
        rows = candidate['items']
        require(isinstance(rows, dict) and set(rows) == {i['id'] for i in ITEMS}, 'All ten rubric items are required exactly once')
        for item in ITEMS:
            row = rows[item['id']]
            where = f"{candidate['id']}.{item['id']}"
            verdict_row(row, ('verdict', 'reason', 'fix', 'basis'), where, quotable, ui)
            keeps_disclosures(row['reason'] + ' ' + row['fix'], disclosures, where)
            require(row['basis'] in ('observed', 'missing_context'), 'Invalid evidence basis')
            require(row['verdict'] == 'fail' or row['basis'] == 'observed', 'Pass must have observed support and no invented fix')
            if item['id'] == 'topic_match' and not any(context.get(k) for k in ('title', 'video_summary', 'source_reference')):
                require(row['verdict'] == 'fail' and row['basis'] == 'missing_context', 'Video URL alone cannot prove topic match')
            if item['id'] == 'resolution_aspect':
                written = (row['reason'] + ' ' + row['fix']).replace(context.get('target_aspect_ratio') or '\0', '')
                require(not RATIO_CLAIM.search(written), f'{where}: the script measures the ratio and its tolerance and adds them to the '
                        'report; judge only sharpness and detail here and never write a ratio or percentage of your own')
                status = aspect['status']
                if status == 'fail':
                    require(row['verdict'] == 'fail' and row['basis'] == 'observed',
                            f"Actual aspect ratio differs from target by {aspect['deviation_percent']}% (over 1%): resolution_aspect fails")
                else:
                    # pass: the ratio is fine. no_target / screenshot / nonstandard_size: the ratio is not judged and the
                    # report shows it as "to confirm", never as a failure or a first change. The row may still fail for blur.
                    require(row['basis'] == 'observed', f'{where}: the ratio is {status} by the script and is not judged, so it is not '
                            'a missing-context failure; judge sharpness only (pass unless the image is blurry)')
        failed = {k for k, v in rows.items() if v['verdict'] == 'fail'}
        priorities = candidate['priorities']
        require(isinstance(priorities, list) and all(isinstance(v, str) for v in priorities), 'Priority IDs must be strings')
        require(len(set(priorities)) == len(priorities) and set(priorities) <= failed, 'Priorities must be distinct failed items')
        require(min(2, len(failed)) <= len(priorities) <= min(3, len(failed)), 'Pick the first 2–3 fixes; fewer only when fewer items failed')
        require(type(candidate['suitable']) is bool, 'Suitability must be a boolean editorial judgment')
        sentence(candidate['suitability_reason'])
        require(not candidate['suitable'] or len(failed) < len(ITEMS), 'An all-fail candidate cannot be suitable')
        require(not candidate['suitable'] or all(r['basis'] != 'missing_context' for r in rows.values()), 'Missing context cannot establish suitability')
        outcomes[candidate['id']] = {'suitable': candidate['suitable'], 'failed_items': [i['id'] for i in ITEMS if i['id'] in failed], 'aspect': aspect}
    pairs = list(itertools.combinations(ids, 2))
    require(isinstance(review['comparisons'], list) and len(review['comparisons']) == len(pairs), 'Compare every pair exactly once')
    for row, pair in zip(review['comparisons'], pairs):
        keys(row, ('pair', 'winner', 'reason'), 'comparison ' + '/'.join(pair))
        require(row['pair'] == list(pair) and row['winner'] in (*pair, 'tie', 'neither', 'insufficient'), 'Invalid pair or winner')
        sentence(row['reason'])
        grounded(row['reason'], seen_by_id[pair[0]] + ' | ' + seen_by_id[pair[1]] + ' | ' + title_seen, f'Comparison {pair[0]}/{pair[1]}', ui_by_id[pair[0]] + ui_by_id[pair[1]])
        eligible = [i for i in pair if outcomes[i]['suitable']]
        require(row['winner'] not in pair or row['winner'] in eligible, 'Cannot prefer an unsuitable image')
        require(row['winner'] != 'tie' or len(eligible) == 2, 'Tie requires two suitable candidates')
        require(eligible or row['winner'] == 'neither', 'Both unsuitable: use neither')
    rec = review['recommendation']
    keys(rec, ('candidate_id', 'reason'), 'recommendation')
    sentence(rec['reason'])
    grounded(rec['reason'], ' | '.join(seen_by_id.values()) + ' | ' + title_seen, 'Recommendation', [t for ui in ui_by_id.values() for t in ui])
    require(rec['candidate_id'] is None or rec['candidate_id'] in ids, 'Unknown recommendation')
    if rec['candidate_id']:
        require(outcomes[rec['candidate_id']]['suitable'], 'Unsuitable candidates cannot be recommended')
        require(all(p['winner'] in (rec['candidate_id'], 'tie') for p in review['comparisons'] if rec['candidate_id'] in p['pair']), 'Recommendation contradicts a pairwise result')
    length = check_title_review(request, review, ids, seen_by_id, ui_by_id)
    if length:
        outcomes['title_length'] = length
    return request, review, outcomes


def text(value):
    # Escape all model and uploaded text so it cannot inject HTML, Markdown links or extra table rows.
    return html.escape(str(value), quote=False).replace('\\', '&#92;').replace('|', '&#124;').replace('[', '&#91;').replace(']', '&#93;').replace('*', '&#42;').replace('`', '&#96;').replace('\n', ' ')


def aspect_sentence(aspect, context, labels):
    """The script's own measurement in the report language; the model never writes these numbers."""
    def number(value, places):
        return f'{value:.{places}f}'.replace('.', labels['decimal_sep'])
    values = {'size': f"{aspect['width']}×{aspect['height']}", 'ratio': number(aspect['ratio'], 3)}
    if 'target' in aspect:
        values.update(target=aspect['target'], target_ratio=number(aspect['target_ratio'], 3), deviation=number(aspect['deviation_percent'], 2),
                      source=labels['source_' + context['target_aspect_source']])
    template = labels['aspect_' + aspect['status']] if aspect['status'] in ('pass', 'fail', 'no_target', 'screenshot') else labels['aspect_nonstandard']
    return template.format(**values)


UNJUDGED = ('no_target', 'screenshot', 'nonstandard_size')


def render(request, review, outcomes):
    labels = check_labels(request)
    names = {i['id']: labels[i['id']] for i in ITEMS}
    word = lambda value: labels.get(value, value)
    row = lambda *cells: '| ' + ' | '.join(cells) + ' |'
    header = [row(labels['col_item'], labels['col_verdict'], labels['col_reason'], labels['col_fix']), '|---|---|---|---|']
    lines = ['# ' + labels['report_title'], '', labels['disclaimer'], '']
    for c in review['candidates']:
        obs = c['observations']
        shown = labels['list_sep'].join(text(t) for t in obs['visible_text']) or labels['no_text']
        aspect = outcomes[c['id']]['aspect']
        lines += ['## ' + c['id'], '', text(c['suitability_reason']), '']
        if aspect['status'] in UNJUDGED:
            # Say up front why the ratio is not judged and what to send, not only inside the table row.
            lines += ['> ' + text(aspect_sentence(aspect, request['context'], labels)), '']
        lines += [labels['text_in_image'] + shown, '']
        if obs['ui_text']:
            lines += [labels['ui_text'] + labels['list_sep'].join(text(t) for t in obs['ui_text']), '']
        lines += header
        for item in ITEMS:
            r = c['items'][item['id']]
            reason, verdict = text(r['reason']), word(r['verdict'])
            if item['id'] == 'resolution_aspect':
                reason += ' ' + text(aspect_sentence(aspect, request['context'], labels))
                if aspect['status'] in UNJUDGED and r['verdict'] == 'pass':
                    verdict = labels['pending']
            lines.append(row(names[item['id']], verdict, reason, text(r['fix']) if r['fix'] else '—'))
        lines += ['', '### ' + labels['change_first'], '']
        if not c['priorities']:
            lines.append(labels['no_changes'])
        for n, ident in enumerate(c['priorities'], 1):
            lines.append(f"{n}. {names[ident]} — {text(c['items'][ident]['fix'])}")
        lines.append('')
    if review['title_review']:
        title, length = review['title_review'], outcomes['title_length']
        long = length['status'] != 'ok'
        lines += ['## ' + labels['title_heading'], '', '> ' + text(title['title']), ''] + header
        lines.append(row(labels['title_length'], word('fail' if long else 'pass'),
                         text(labels['title_length_' + length['status']].format(chars=length['chars'])), text(labels['title_length_fix']) if long else '—'))
        lines.append(row(labels['title_clarity'], word(title['clarity']['verdict']), text(title['clarity']['reason']), text(title['clarity']['fix']) or '—'))
        for pair in title['pairing']:
            lines.append(row(labels['title_pairing'].format(id=pair['candidate_id']), word(pair['verdict']), text(pair['reason']), text(pair['fix']) or '—'))
        lines.append('')
    if review['comparisons']:
        lines += ['## ' + labels['compare'], '']
        for p in review['comparisons']:
            lines.append(f"- {' / '.join(p['pair'])}: {word(p['winner'])} — {text(p['reason'])}")
        lines.append('')
    all_failed = all(not o['suitable'] for k, o in outcomes.items() if k in {c['id'] for c in review['candidates']})
    decision = labels['none_suitable'] if all_failed else (review['recommendation']['candidate_id'] or labels['no_clear'])
    lines += ['## ' + labels['recommendation'], '', decision, '', text(review['recommendation']['reason']), '']
    return '\n'.join(lines)


def deliver(run):
    for name in FINAL:
        (run / name).unlink(missing_ok=True)
    request, review, outcomes = validate(run)
    report = render(request, review, outcomes)
    receipt = {'schema_version': 'review-thumbnail.delivery.v3', 'status': 'validated', 'report_path': str((run / FINAL[0]).resolve()),
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
