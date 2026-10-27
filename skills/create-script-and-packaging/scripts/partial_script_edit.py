#!/usr/bin/env python3
"""Freeze a conversation script and validate scoped cover/opening alternatives.

This contract deliberately carries no SelectedIdea or production approval. It is
an edit proposal for a named source revision, not a newly approved ScriptPackage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import copy
from pathlib import Path


def digest(text):
    """Hash the exact UTF-8 source text so edits cannot target another revision."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def nonempty(value):
    """Accept only strings containing visible non-whitespace content."""
    return isinstance(value, str) and bool(value.strip())


def authorized_changes(text, boundary, source_reference):
    """Validate a caller-reviewed intent boundary against the exact current message.

    This checks provenance and structure, not natural-language interpretation.
    The caller must resolve negation, quotations and ambiguity before freezing.
    """
    fields = {'cover_text', 'opening'}
    if not nonempty(text) or not isinstance(boundary, dict):
        raise ValueError('Missing structured user-authorized scope boundary')
    if set(boundary) != {'message_sha256', 'source_span', 'entries', 'excluded', 'unresolved'}:
        raise ValueError('Invalid user-authorized scope boundary fields')
    if boundary['message_sha256'] != digest(text):
        raise ValueError('User-authorized scope boundary targets a different message')
    def span(value):
        """Require an exact nonempty Unicode code-point span in the frozen message."""
        if not isinstance(value, dict) or set(value) != {'start', 'end', 'text'}:
            raise ValueError('Authorization needs an exact text span')
        start, end, quote = value['start'], value['end'], value['text']
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                or not nonempty(quote) or text[start:end] != quote):
            raise ValueError('Authorization span differs from the frozen user text')
        return start, end
    source_start, source_end = span(boundary['source_span'])
    if boundary['source_span']['text'] != source_reference:
        raise ValueError('Authorization source span must equal source_reference')
    excluded, unresolved, entries = boundary['excluded'], boundary['unresolved'], boundary['entries']
    if (not isinstance(excluded, list) or not all(isinstance(x, str) and x in fields for x in excluded)
            or len(excluded) != len(set(excluded))):
        raise ValueError('Invalid excluded edit surfaces')
    if not isinstance(unresolved, list) or unresolved:
        raise ValueError('Cannot freeze unresolved edit authorization')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Missing explicit user-authorized scope entries')
    changes, evidence = {}, []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'change', 'count', 'span'}:
            raise ValueError('Invalid user-authorized scope entry')
        field, count = entry['change'], entry['count']
        if not isinstance(field, str) or field not in fields:
            raise ValueError('Only cover_text and opening alternatives are supported')
        if type(count) is not int or not 1 <= count <= 50:
            raise ValueError('Alternative counts must be integers from 1 to 50')
        if field in changes or field in excluded:
            raise ValueError('Conflicting user-authorized scope entries')
        start, end = span(entry['span'])
        if max(start, source_start) < min(end, source_end):
            raise ValueError('A source title does not authorize an edit')
        changes[field] = count
        evidence.append(copy.deepcopy(entry))
    return changes, evidence


def adapt(request, conversation):
    """Freeze an earlier conversation script and the current user-authorized edit scope."""
    if request.get('schema_version') != 'partial-script-edit-request.v1':
        raise ValueError('Expected partial-script-edit-request.v1')
    for key in ('request_id', 'source_message_id', 'request_message_id', 'source_version', 'language', 'source_reference'):
        if not nonempty(request.get(key)):
            raise ValueError(f'Missing {key}')
    messages = conversation.get('messages', [])
    ids = [m.get('id') for m in messages]
    if len(ids) != len(set(ids)) or any(not nonempty(i) for i in ids):
        raise ValueError('Conversation message IDs must be unique and nonempty')
    try:
        source_index = ids.index(request['source_message_id'])
        target_index = ids.index(request['request_message_id'])
    except ValueError as exc:
        raise ValueError('Source and requesting turn must exist in the frozen conversation') from exc
    source, target = messages[source_index], messages[target_index]
    if source_index >= target_index or target.get('role') != 'user':
        raise ValueError('Source must precede the user edit request')
    if source.get('role') not in ('user', 'assistant') or not nonempty(source.get('text')):
        raise ValueError('Source must be an actual user or assistant script')
    if request['source_version'] != digest(source['text']):
        raise ValueError('source_version must equal the exact source text SHA256')
    # This is an auditable reference, not a claim that approval can be inferred by code.
    if request['source_reference'] not in target.get('text', ''):
        raise ValueError('source_reference must be verbatim from the current user request')
    scope = request.get('changes')
    if not isinstance(scope, dict) or not scope or set(scope) - {'cover_text', 'opening'}:
        raise ValueError('Only cover_text and opening alternatives are supported')
    if any(type(n) is not int or not 1 <= n <= 50 for n in scope.values()):
        raise ValueError('Alternative counts must be integers from 1 to 50')
    authorized_scope, scope_evidence = authorized_changes(target.get('text'), request.get('authorization_boundary'), request['source_reference'])
    if scope != authorized_scope:
        raise ValueError('Requested changes do not match the user-authorized scope and count')
    if request.get('cover_deliverable') not in ('text', 'none'):
        raise ValueError('Image covers require actual image artifacts; this adapter produces text only')
    if ('cover_text' in scope) != (request['cover_deliverable'] == 'text'):
        raise ValueError('Cover deliverable must match requested changes')
    return {'schema_version': 'partial-script-edit-input.v1', 'request_id': request['request_id'],
            'language': request['language'], 'source': {'message_id': source['id'],
            'role': source['role'], 'version': digest(source['text']), 'text': source['text']},
            'authorization': {'message_id': target['id'], 'text': target['text'],
                              'source_reference': request['source_reference'],
                              'basis': 'user_requested_revision', 'production_approval': False,
                              'scope_evidence': scope_evidence,
                              'boundary': copy.deepcopy(request['authorization_boundary'])},
            'changes': scope, 'cover_deliverable': request['cover_deliverable']}


def validate(result, frozen):
    """Reject source drift, body changes, approval claims, or alternatives outside the frozen scope."""
    authorized_scope, scope_evidence = authorized_changes(frozen['authorization']['text'], frozen['authorization'].get('boundary'), frozen['authorization']['source_reference'])
    if frozen['changes'] != authorized_scope or frozen['authorization'].get('scope_evidence') != scope_evidence:
        raise ValueError('Frozen changes do not match the user-authorized scope and count')
    if result.get('schema_version') != 'partial-script-edit.v1':
        raise ValueError('Expected partial-script-edit.v1')
    if result.get('source_version') != frozen['source']['version']:
        raise ValueError('Edit targets a different source revision')
    if result.get('preserved_script') != frozen['source']['text']:
        raise ValueError('Unrequested script text was changed')
    if result.get('status') != 'proposal' or result.get('approval_status') != 'pending':
        raise ValueError('Alternatives are pending proposals, never production approval')
    if result.get('language') != frozen['language']:
        raise ValueError('Edit language mismatch')
    changes = result.get('alternatives')
    if not isinstance(changes, dict) or set(changes) != set(frozen['changes']):
        raise ValueError('Output changes exceed or omit the requested scope')
    for field, count in frozen['changes'].items():
        values = changes[field]
        if not isinstance(values, list) or len(values) != count or not all(nonempty(v) for v in values):
            raise ValueError(f'{field}: expected {count} nonempty text alternatives')
        if len(set(' '.join(v.split()).casefold() for v in values)) != count:
            raise ValueError(f'{field}: duplicate alternatives')
    for field in ('title', 'selection_prompt', 'boundary_note'):
        if not nonempty(result.get(field)):
            raise ValueError(f'Missing localized {field}')
    if not isinstance(result.get('labels'), dict) or set(result['labels']) != set(changes) or not all(nonempty(v) for v in result['labels'].values()):
        raise ValueError('Localized labels must cover exactly the changed surfaces')


def render(result, frozen):
    """Render every validated alternative and its localized selection interaction."""
    validate(result, frozen)
    lines = ['# ' + result['title'], '', result['boundary_note'], '']
    for field, values in result['alternatives'].items():
        lines.extend(['## ' + result['labels'][field], ''])
        lines.extend(f'{i}. {value}' for i, value in enumerate(values, 1))
        lines.append('')
    lines.append(result['selection_prompt'])
    return '\n'.join(lines) + '\n'


def main():
    """Read frozen inputs and optionally validate and render a partial edit proposal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--conversation', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    if args.result:
        if not args.report:
            parser.error('--result requires --report')
        frozen = load(args.input)
        if frozen != adapt(load(args.request), load(args.conversation)):
            raise ValueError('Request or conversation differs from the frozen edit input')
        text = render(load(args.result), frozen)
        args.report.write_text(text, encoding='utf-8')
    else:
        frozen = adapt(load(args.request), load(args.conversation))
        with args.input.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n')


if __name__ == "__main__":
    main()
