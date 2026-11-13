"""Synthetic contract checks; these are not visual accuracy evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
from PIL import Image
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('review_thumbnail', ROOT / 'skills/review-thumbnail/scripts/review_thumbnail.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Contract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        for i, color in zip('ABC', ('red', 'green', 'blue')):
            Image.new('RGB', (160, 90), color).save(self.root / (i + '.png'))
        self.source = dict(images=['A.png', 'B.png', 'C.png'], language='en', context={'title':'A topic', 'target_aspect_ratio':'16:9'})
        m.write(self.root / 'input.json', self.source)
        m.prepare(self.root / 'input.json', self.run)
        self.review = dict(schema_version='review-thumbnail.review.v2', request_sha256=m.digest((self.run / 'request.json').read_bytes()), candidates=[dict(id=i, observations=dict(visible_text=['TOPIC '+i, 'AI generated'], main_subject='A plain colored test card.', disclosures=['AI generated']), items={j['id']:dict(verdict='pass', reason='Concrete visible feature.', fix='', basis='observed') for j in m.ITEMS}, priorities=[], suitable=True, suitability_reason='Clear topic and finished layout.') for i in 'ABC'], comparisons=[dict(pair=list(p), winner=p[0], reason='The first has a clearer subject; the second has competing text.') for p in [('A','B'),('A','C'),('B','C')]], recommendation=dict(candidate_id='A', reason='Clearer than both alternatives.'))
        self.save()

    def save(self): m.write(self.run / 'review.json', self.review)

    def bad(self, edit):
        m.deliver(self.run)
        edit(self.review)
        self.save()
        with self.assertRaises((ValueError, TypeError, KeyError)):
            m.deliver(self.run)
        self.assertFalse((self.run / 'FINAL_REVIEW.md').exists())
        self.assertFalse((self.run / 'delivery.json').exists())

    def fail(self, idx, ids):
        c = self.review['candidates'][idx]
        for ident in ids:
            c['items'][ident].update(verdict='fail', fix='Remove the competing element.')
        c['priorities'] = ids[:3]

    def context(self, context):
        request=m.load(self.run/'request.json');request['context']=context
        m.write(self.run/'request.json',request)
        self.review['request_sha256']=m.digest((self.run/'request.json').read_bytes())

    def test_delivery_is_complete_and_stable(self):
        receipt=m.deliver(self.run);report=(self.run/'FINAL_REVIEW.md').read_bytes()
        self.assertEqual(m.digest(report),receipt['report_sha256'])
        self.assertEqual(report.count(b'Concrete visible feature.'),30)
        self.assertEqual(m.deliver(self.run)['report_sha256'],receipt['report_sha256'])
        self.assertNotIn(b'| Score |',report)

    def test_observations_are_required(self):
        self.bad(lambda r: r['candidates'][0].pop('observations'))

    def test_disclosure_must_be_in_visible_text(self):
        self.bad(lambda r: r['candidates'][0]['observations'].update(disclosures=['cloned voice']))

    def test_quoted_text_must_come_from_same_candidate(self):
        # 回归：三图对比时把 A 的标题安到 C 上。
        self.bad(lambda r: r['candidates'][2]['items']['topic_match'].update(reason='The headline “TOPIC A” matches the topic.'))

    def test_quoted_text_from_own_candidate_passes(self):
        self.review['candidates'][2]['items']['topic_match'].update(reason='The headline “TOPIC C” matches the topic.')
        self.save()
        m.deliver(self.run)

    def test_comparison_quotes_must_belong_to_the_pair(self):
        self.bad(lambda r: r['comparisons'][0].update(reason='A wins because “TOPIC C” is clearer.'))

    def test_cannot_ask_to_remove_disclosure(self):
        # 回归：把“AI generated”来源标识当杂物要求删除。
        def edit(r):
            c=r['candidates'][0];c['items']['execution'].update(verdict='fail',reason='The AI generated label looks like leftover clutter.',fix='Remove the AI generated label.');c['priorities']=['execution']
        self.bad(edit)

    def test_moving_disclosure_is_allowed(self):
        c=self.review['candidates'][0];c['items']['uncluttered'].update(verdict='fail',reason='The AI generated label overlaps the face.',fix='Move the AI generated label to a corner and keep it readable.');c['priorities']=['uncluttered']
        self.save()
        m.deliver(self.run)

    def test_report_lists_visible_text(self):
        m.deliver(self.run)
        self.assertIn(b'Text in image: TOPIC A', (self.run/'FINAL_REVIEW.md').read_bytes())

    def test_single_candidate(self):
        request=m.load(self.run/'request.json');request['images']=request['images'][:1];m.write(self.run/'request.json',request)
        self.review['request_sha256']=m.digest((self.run/'request.json').read_bytes())
        self.review['candidates']=self.review['candidates'][:1];self.review['comparisons']=[]
        self.save();m.deliver(self.run)

    def test_two_candidates(self):
        request=m.load(self.run/'request.json');request['images']=request['images'][:2];m.write(self.run/'request.json',request)
        self.review['request_sha256']=m.digest((self.run/'request.json').read_bytes())
        self.review['candidates']=self.review['candidates'][:2];self.review['comparisons']=self.review['comparisons'][:1]
        self.save();m.deliver(self.run)

    def test_missing_item(self): self.bad(lambda r:r['candidates'][0]['items'].pop('emotion'))
    def test_unknown_item(self): self.bad(lambda r:r['candidates'][0]['items'].update(extra={}))
    def test_numeric_score(self): self.bad(lambda r:r['candidates'][0]['items']['emotion'].update(score=5))
    def test_third_verdict(self): self.bad(lambda r:r['candidates'][0]['items']['emotion'].update(verdict='unknown'))
    def test_blank_reason(self): self.bad(lambda r:r['candidates'][0]['items']['emotion'].update(reason=' '))
    def test_missing_fix(self): self.bad(lambda r:r['candidates'][0]['items']['emotion'].update(verdict='fail'))
    def test_pass_with_fix(self): self.bad(lambda r:r['candidates'][0]['items']['emotion'].update(fix='Make it better.'))
    def test_pass_missing_context(self): self.bad(lambda r:r['candidates'][0]['items']['emotion'].update(basis='missing_context'))
    def test_wrong_priority(self): self.bad(lambda r:r['candidates'][0].update(priorities=['emotion']))
    def test_single_failure_needs_only_one_priority(self):
        self.fail(0,['emotion']);self.save();m.deliver(self.run)
    def test_three_failures_need_two_or_three(self):
        self.fail(0,['emotion','harmony','curiosity']);self.review['candidates'][0]['priorities'].pop();self.save();m.deliver(self.run)
        self.bad(lambda r:r['candidates'][0].update(priorities=['emotion']))
    def test_duplicate_priority(self):
        self.fail(0,['emotion','harmony']);self.save()
        self.bad(lambda r:r['candidates'][0].update(priorities=['emotion','emotion']))
    def test_missing_candidate(self): self.bad(lambda r:r['candidates'].pop())
    def test_duplicate_candidate(self): self.bad(lambda r:r['candidates'][1].update(id='A'))
    def test_missing_pair(self): self.bad(lambda r:r['comparisons'].pop())
    def test_duplicate_pair(self): self.bad(lambda r:r['comparisons'][1].update(pair=['A','B']))
    def test_contradictory_winner(self): self.bad(lambda r:r['comparisons'][0].update(winner='B'))
    def test_no_forced_winner(self):
        self.review['recommendation']['candidate_id']=None
        self.review['comparisons'][1]['winner']='C'
        self.save();m.deliver(self.run)
    def test_all_unsuitable(self):
        for i in range(3):
            self.fail(i,['execution','uncluttered'])
            self.review['candidates'][i]['suitable']=False
        for row in self.review['comparisons']:row['winner']='neither'
        self.review['recommendation']['candidate_id']=None
        self.save();m.deliver(self.run)
        self.assertIn('None is suitable',(self.run/'FINAL_REVIEW.md').read_text())
        self.bad(lambda r:r['recommendation'].update(candidate_id='A'))
    def test_url_only_not_topic_evidence(self):
        self.context({'video_url':'https://example.org/video','target_aspect_ratio':'16:9'});self.save()
        with self.assertRaises(ValueError):m.deliver(self.run)
    def test_missing_context_is_explicit(self):
        self.context({})
        for i in range(3):
            self.fail(i,['topic_match','resolution_aspect'])
            for key in ['topic_match','resolution_aspect']:
                self.review['candidates'][i]['items'][key].update(basis='missing_context',reason='Missing evidence; cannot confirm.',fix='Provide the topic and intended format.')
            self.review['candidates'][i]['suitable']=False
        for p in self.review['comparisons']:p['winner']='neither'
        self.review['recommendation']['candidate_id']=None
        self.save();m.deliver(self.run)
    def test_wrong_ratio_cannot_pass(self):
        self.context({'title':'A topic','target_aspect_ratio':'9:16'});self.save()
        with self.assertRaises(ValueError):m.deliver(self.run)
    def test_invalid_ratio(self):
        self.source['context']['target_aspect_ratio']='0:9';m.write(self.root/'input.json',self.source)
        with self.assertRaises(ValueError):m.prepare(self.root/'input.json',self.root/'new')
    def test_input_mutation_removes_old_report(self):
        m.deliver(self.run);(self.run/'A.source.png').write_bytes((self.run/'B.source.png').read_bytes());self.save()
        with self.assertRaises(ValueError):m.deliver(self.run)
        self.assertFalse((self.run/'delivery.json').exists())
    def test_stale_request(self):
        m.deliver(self.run);p=self.run/'request.json';p.write_text(p.read_text()+' ')
        with self.assertRaises(ValueError):m.deliver(self.run)
    def test_dimensions_not_trusted(self):
        request=m.load(self.run/'request.json');request['images'][0]['width']=100;m.write(self.run/'request.json',request)
        self.review['request_sha256']=m.digest((self.run/'request.json').read_bytes());self.save()
        with self.assertRaises(ValueError):m.deliver(self.run)
    def test_escaped_injection(self):
        self.review['candidates'][0]['items']['emotion']['reason']='<script>alert(1)</script> | [click](evil)'
        self.save();m.deliver(self.run);s=(self.run/'FINAL_REVIEW.md').read_text()
        self.assertNotIn('<script>',s);self.assertNotIn('[click]',s);self.assertIn('&#124;',s)
    def test_duplicate_json_keys(self):
        (self.run/'review.json').write_text('{"candidates":[],"candidates":[]}')
        with self.assertRaises(ValueError):m.deliver(self.run)
    def test_old_schema_rejected(self): self.bad(lambda r:r.update(schema_version='review-thumbnail.review.v1'))
    def test_duplicate_images_rejected(self):
        self.source['images']=['A.png','A.png'];m.write(self.root/'input.json',self.source)
        with self.assertRaises(ValueError):m.prepare(self.root/'input.json',self.root/'new')
    def test_run_not_reused(self):
        with self.assertRaises(ValueError):m.prepare(self.root/'input.json',self.run)
    def test_path_escape(self):
        request=m.load(self.run/'request.json');request['images'][0]['path']='../A.png';m.write(self.run/'request.json',request)
        with self.assertRaises(ValueError):m.deliver(self.run)
    def test_chinese_ten_labels(self):
        request=m.load(self.run/'request.json');request['language']='zh';m.write(self.run/'request.json',request)
        self.review['request_sha256']=m.digest((self.run/'request.json').read_bytes());self.save();m.deliver(self.run)
        s=(self.run/'FINAL_REVIEW.md').read_text()
        for label in ['主题匹配','情绪触发','视觉协调','吸睛元素','构图简洁','色彩与对比','独特概念','创意执行','引发好奇','分辨率与比例']:
            self.assertEqual(s.count('| '+label+' |'),3)
        self.assertNotIn('分数',s)

if __name__=='__main__':unittest.main()
