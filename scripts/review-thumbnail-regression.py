"""Synthetic contract checks; these are not visual accuracy evidence."""
import importlib.util
import itertools
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


def title_review(title, ids):
    return dict(title=title, clarity=dict(verdict='pass', reason='The title names the topic plainly.', fix=''),
                pairing=[dict(candidate_id=i, verdict='pass', reason='The image shows what the title promises without repeating it.', fix='') for i in ids])


class Contract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        for i, color in zip('ABC', ('red', 'green', 'blue')):
            Image.new('RGB', (160, 90), color).save(self.root / (i + '.png'))
        self.source = dict(images=['A.png', 'B.png', 'C.png'], language='en', context={'title':'A topic', 'target_aspect_ratio':'16:9', 'target_aspect_source':'user'})
        m.write(self.root / 'input.json', self.source)
        m.prepare(self.root / 'input.json', self.run)
        self.review = dict(schema_version='review-thumbnail.review.v3', request_sha256=m.digest((self.run / 'request.json').read_bytes()), candidates=[dict(id=i, observations=dict(capture='original', visible_text=['TOPIC '+i, 'AI generated'], ui_text=[], main_subject='A plain colored test card.', disclosures=['AI generated']), items={j['id']:dict(verdict='pass', reason='Concrete visible feature.', fix='', basis='observed') for j in m.ITEMS}, priorities=[], suitable=True, suitability_reason='Clear topic and finished layout.') for i in 'ABC'], title_review=title_review('A topic', 'ABC'), comparisons=[dict(pair=list(p), winner=p[0], reason='The first has a clearer subject; the second has competing text.') for p in [('A','B'),('A','C'),('B','C')]], recommendation=dict(candidate_id='A', reason='Clearer than both alternatives.'))
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
        # Regression: a three-image comparison attributed A's headline to C.
        self.bad(lambda r: r['candidates'][2]['items']['topic_match'].update(reason='The headline “TOPIC A” matches the topic.'))

    def test_quoted_text_from_own_candidate_passes(self):
        self.review['candidates'][2]['items']['topic_match'].update(reason='The headline “TOPIC C” matches the topic.')
        self.save()
        m.deliver(self.run)

    def test_comparison_quotes_must_belong_to_the_pair(self):
        self.bad(lambda r: r['comparisons'][0].update(reason='A wins because “TOPIC C” is clearer.'))

    def test_cannot_ask_to_remove_disclosure(self):
        # Regression: an "AI generated" source label was treated as clutter and the review asked to remove it.
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
        self.review['candidates']=self.review['candidates'][:1];self.review['comparisons']=[];self.review['title_review']=title_review('A topic','A')
        self.save();m.deliver(self.run)

    def test_two_candidates(self):
        request=m.load(self.run/'request.json');request['images']=request['images'][:2];m.write(self.run/'request.json',request)
        self.review['request_sha256']=m.digest((self.run/'request.json').read_bytes())
        self.review['candidates']=self.review['candidates'][:2];self.review['comparisons']=self.review['comparisons'][:1];self.review['title_review']=title_review('A topic','AB')
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
        self.context({'video_url':'https://example.org/video','target_aspect_ratio':'16:9','target_aspect_source':'user'});self.review['title_review']=None;self.save()
        with self.assertRaises(ValueError):m.deliver(self.run)
    def test_missing_context_is_explicit(self):
        self.context({});self.review['title_review']=None
        for i in range(3):
            self.fail(i,['topic_match'])
            self.review['candidates'][i]['items']['topic_match'].update(basis='missing_context',reason='Missing evidence; cannot confirm.',fix='Provide the topic.')
            self.review['candidates'][i]['suitable']=False
        for p in self.review['comparisons']:p['winner']='neither'
        self.review['recommendation']['candidate_id']=None
        self.save();m.deliver(self.run)
    def test_wrong_ratio_cannot_pass(self):
        self.context({'title':'A topic','target_aspect_ratio':'9:16','target_aspect_source':'user'});self.save()
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
    def test_old_schema_rejected(self): self.bad(lambda r:r.update(schema_version='review-thumbnail.review.v2'))
    def test_duplicate_images_rejected(self):
        self.source['images']=['A.png','A.png'];m.write(self.root/'input.json',self.source)
        with self.assertRaises(ValueError):m.prepare(self.root/'input.json',self.root/'new')
    def test_run_not_reused(self):
        with self.assertRaises(ValueError):m.prepare(self.root/'input.json',self.run)
    def test_input_folder_is_not_a_run_dir(self):
        # Hosts write request-input.json into a working folder and then pass `--run-dir .`; the error must name the fix.
        with self.assertRaisesRegex(ValueError, r'--run-dir review'):m.prepare(self.root/'input.json',self.root)
        self.assertFalse((self.root/'request.json').exists())
        skill=(ROOT/'skills/review-thumbnail/SKILL.md').read_text()
        self.assertIn('--run-dir review',skill);self.assertNotIn("--run-dir '.'",skill);self.assertNotIn('--run-dir .\n',skill)
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


class ProductionCases(unittest.TestCase):
    """Shapes of production rounds after 1.0.51 (review-thumbnail 0.1.5)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def prepare(self, sizes, context, language='pt-BR', labels=None, name='run'):
        names = []
        for n, (size, color) in enumerate(zip(sizes, ('red', 'green', 'blue'))):
            Image.new('RGB', size, color).save(self.root / f'{n}.png')
            names.append(f'{n}.png')
        source = dict(images=names, language=language, context=context)
        if labels is not None:
            source['labels'] = labels
        m.write(self.root / 'input.json', source)
        run = self.root / name
        prepared = m.prepare(self.root / 'input.json', run)
        return run, prepared

    def review(self, run, ids, capture='original', ui=(), title=None, aspect=None):
        items = {j['id']: dict(verdict='pass', reason='Detalhe visível concreto.', fix='', basis='observed') for j in m.ITEMS}
        if aspect:
            items['resolution_aspect'] = aspect
        failed = [k for k, v in items.items() if v['verdict'] == 'fail']
        review = dict(schema_version='review-thumbnail.review.v3', request_sha256=m.digest((run / 'request.json').read_bytes()),
                      candidates=[dict(id=i, observations=dict(capture=capture, visible_text=['MITO X REALIDADE'], ui_text=list(ui), main_subject='Uma pirâmide em construção.', disclosures=[]),
                                       items=json.loads(json.dumps(items)), priorities=failed[:3], suitable=True, suitability_reason='Tema claro e layout acabado.') for i in ids],
                      title_review=title, comparisons=[dict(pair=list(p), winner=p[0], reason='A tem o foco mais claro; B tem texto concorrente.') for p in itertools.combinations(ids, 2)],
                      recommendation=dict(candidate_id='A', reason='O foco de A é o mais claro.'))
        m.write(run / 'review.json', review)
        return review

    def report(self, run):
        m.deliver(run)
        return (run / 'FINAL_REVIEW.md').read_text()

    # Fix 1 (8c3a710c, 8c61a39a, 50ea3c0c): a supplied title is reviewed with the cover.
    def test_title_is_reviewed_with_the_cover(self):
        title = 'A Vida Real de Quem Ergueu as Pirâmides | Mito x Realidade'
        run, prepared = self.prepare([(2752, 1536)], {'title': title, 'target_aspect_ratio': '16:9', 'target_aspect_source': 'format'})
        self.assertEqual(prepared['title_length']['status'], 'ok')
        self.assertIn('title_review', prepared['next'])
        self.review(run, 'A')
        with self.assertRaisesRegex(ValueError, 'title_review must review it'):
            m.deliver(run)
        pairing = [dict(candidate_id='A', verdict='fail', reason='O título promete “Mito x Realidade”, mas a capa só mostra o mito.', fix='Mostre também o lado da realidade.')]
        self.review(run, 'A', title=dict(title=title, clarity=dict(verdict='pass', reason='Diz o tema e o formato.', fix=''), pairing=pairing))
        report = self.report(run)
        self.assertIn('## Título', report)
        self.assertIn('| Tamanho | aprovado | 58 caracteres', report)
        self.assertIn('| Título + A | reprovado |', report)
        self.assertIn('| Clareza | aprovado |', report)

    def test_title_review_must_use_the_exact_title_and_every_candidate(self):
        run, _ = self.prepare([(1280, 720), (1280, 721)], {'title': 'Exact title', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'})
        clarity = dict(verdict='pass', reason='Clear.', fix='')
        one = [dict(candidate_id='A', verdict='pass', reason='Pairs well.', fix='')]
        self.review(run, 'AB', title=dict(title='Exact title', clarity=clarity, pairing=one))
        with self.assertRaisesRegex(ValueError, 'one row per candidate'):
            m.deliver(run)
        self.review(run, 'AB', title=dict(title='Another title', clarity=clarity, pairing=one + [dict(one[0], candidate_id='B')]))
        with self.assertRaisesRegex(ValueError, 'exact title'):
            m.deliver(run)

    def test_title_length_is_measured_by_the_script(self):
        long = 'Como os trabalhadores das pirâmides comiam, dormiam e eram pagos de verdade no Egito'
        run, prepared = self.prepare([(1280, 720)], {'title': long})
        self.assertEqual(prepared['title_length']['status'], 'long')
        self.review(run, 'A', title=dict(title=long, clarity=dict(verdict='pass', reason='Claro.', fix=''), pairing=[dict(candidate_id='A', verdict='pass', reason='Combina.', fix='')]))
        report = self.report(run)
        self.assertIn(f'| Tamanho | reprovado | {len(long)} caracteres; a busca', report)
        self.assertEqual(m.title_length('x' * 101)['status'], 'over')
        self.assertEqual(m.title_length('封面' * 17)['status'], 'ok')
        self.assertEqual(m.title_length('封面' * 18)['status'], 'long')

    def test_no_title_means_no_title_review(self):
        run, prepared = self.prepare([(1280, 720)], {'video_summary': 'Pyramids', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'})
        self.assertNotIn('title_length', prepared)
        self.review(run, 'A', title=dict(title='x', clarity=dict(verdict='pass', reason='Clear.', fix=''), pairing=[]))
        with self.assertRaisesRegex(ValueError, 'title_review must be null'):
            m.deliver(run)

    # Fix 2 (da3ba5cc): screenshots skip the ratio verdict and platform interface text is not cover text.
    def test_nonstandard_screenshot_sizes_skip_the_ratio_verdict(self):
        run, prepared = self.prepare([(749, 407), (740, 443)], {'video_summary': 'Duas capas para o mesmo vídeo.'})
        self.assertEqual([x['status'] for x in prepared['measurements']], ['nonstandard_size', 'nonstandard_size'])
        self.review(run, 'AB', aspect=dict(verdict='fail', reason='Sem formato informado.', fix='Informe o formato.', basis='missing_context'))
        with self.assertRaisesRegex(ValueError, 'not a missing-context failure'):
            m.deliver(run)
        self.review(run, 'AB')
        report = self.report(run)
        self.assertIn('749×407 (1,840:1) não é um tamanho padrão de thumbnail', report)
        self.assertNotIn('solicitado', report)
        self.assertNotIn('pediu', report)

    def test_a_ratio_needs_its_source(self):
        with self.assertRaisesRegex(ValueError, 'target_aspect_source'):
            self.prepare([(749, 407)], {'video_summary': 'x', 'target_aspect_ratio': '16:9'})

    def test_a_ratio_the_creator_did_not_name_is_not_called_requested(self):
        run, _ = self.prepare([(1280, 720)], {'title': 'Pirâmides', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'format'})
        self.review(run, 'A', title=dict(title='Pirâmides', clarity=dict(verdict='pass', reason='Claro.', fix=''), pairing=[dict(candidate_id='A', verdict='pass', reason='Combina.', fix='')]))
        report = self.report(run)
        self.assertIn('o padrão do formato citado na conversa', report)
        self.assertNotIn('como você pediu', report)

    def test_list_card_screenshot_keeps_interface_text_apart(self):
        ui = ['12:31', 'A Vida Real de Quem Ergueu as Pirâmides', '1,2 mil visualizações']
        run, prepared = self.prepare([(431, 326)], {'title': 'A Vida Real de Quem Ergueu as Pirâmides'})
        self.assertEqual(prepared['measurements'][0]['status'], 'no_target')
        title = dict(title='A Vida Real de Quem Ergueu as Pirâmides', clarity=dict(verdict='pass', reason='Claro.', fix=''),
                     pairing=[dict(candidate_id='A', verdict='pass', reason='A capa mostra a obra que o título promete.', fix='')])
        self.review(run, 'A', capture='screenshot', ui=ui, title=title)
        doc = json.loads((run / 'review.json').read_text())
        doc['candidates'][0]['items']['uncluttered'].update(verdict='fail', reason='O texto “12:31” compete com o rosto.', fix='Tire o selo.')
        doc['candidates'][0]['priorities'] = ['uncluttered']
        m.write(run / 'review.json', doc)
        with self.assertRaisesRegex(ValueError, 'platform interface text'):
            m.deliver(run)
        self.review(run, 'A', capture='original', ui=ui, title=title)
        with self.assertRaisesRegex(ValueError, 'only for a screenshot'):
            m.deliver(run)
        self.review(run, 'A', capture='screenshot', ui=ui, title=title)
        report = self.report(run)
        self.assertIn('Texto na imagem: MITO X REALIDADE\n', report)
        self.assertIn('Interface da plataforma na captura (não faz parte da capa e não foi avaliada): 12:31; ', report)
        self.assertIn('> Esta é uma captura de tela (431×326)', report)
        self.assertIn('| Resolução e proporção | a confirmar |', report)
        self.assertNotIn('1. Resolução e proporção', report)

    # Fix 3 (8c3a710c): the script decides the ratio; 2752x1536 is 0.78% from 16:9 and passes.
    def test_ratio_within_tolerance_is_decided_by_the_script(self):
        run, prepared = self.prepare([(2752, 1536)], {'video_summary': 'Pirâmides', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'})
        self.assertEqual(prepared['measurements'][0]['status'], 'pass')
        self.assertEqual(prepared['measurements'][0]['deviation_percent'], 0.78)
        wrong = dict(verdict='fail', reason='A imagem tem proporção aproximada de 1,792:1, acima da tolerância de 1% para 16:9.', fix='Recorte para 2731 × 1536.', basis='observed')
        self.review(run, 'A', aspect=wrong)
        with self.assertRaisesRegex(ValueError, 'never write a ratio or percentage'):
            m.deliver(run)
        self.review(run, 'A')
        report = self.report(run)
        self.assertIn('| Resolução e proporção | aprovado | Detalhe visível concreto. Medido pelo script: 2752×1536 (1,792:1); alvo 16:9 (1,778:1), como você pediu. Diferença de 0,78%, dentro da tolerância de 1%', report)
        blurry = dict(verdict='fail', reason='Os rostos ficam borrados no tamanho pequeno.', fix='Exporte com mais nitidez em 16:9.', basis='observed')
        self.review(run, 'A', aspect=blurry)
        self.assertIn('| Resolução e proporção | reprovado | Os rostos ficam borrados', self.report(run))

    def test_ratio_over_tolerance_must_fail(self):
        run, prepared = self.prepare([(1080, 1920)], {'video_summary': 'x', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'})
        self.assertEqual(prepared['measurements'][0]['status'], 'fail')
        self.review(run, 'A')
        with self.assertRaisesRegex(ValueError, 'over 1%'):
            m.deliver(run)

    # Fix 4: fixed labels follow the creator's language.
    def test_portuguese_labels(self):
        run, _ = self.prepare([(1280, 720), (1280, 720 + 1)], {'video_summary': 'x', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'})
        self.review(run, 'AB')
        report = self.report(run)
        for label in ['# Avaliação de thumbnail', '| Item | Resultado | Motivo | Como melhorar |', '| Relação com o tema | aprovado |', '## Comparação', '## Recomendação']:
            self.assertIn(label, report)
        for english in ['Thumbnail review', '| Verdict |', '| pass |', 'Text in image', 'Change first']:
            self.assertNotIn(english, report)

    def test_traditional_chinese_labels(self):
        run, _ = self.prepare([(1280, 720)], {'video_summary': 'x', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'}, language='zh-TW')
        self.review(run, 'A')
        report = self.report(run)
        self.assertIn('# 封面評測', report)
        self.assertIn('| 解析度與比例 | 過 |', report)
        self.assertNotIn('封面评测', report)

    def test_other_languages_supply_validated_labels(self):
        context = {'video_summary': 'x', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'}
        with self.assertRaisesRegex(ValueError, 'never fall back to English'):
            self.prepare([(1280, 720)], context, language='tr')
        with self.assertRaisesRegex(ValueError, 'still English'):
            self.prepare([(1280, 720)], context, language='tr', labels=dict(m.CATALOGS['en']))
        turkish = {k: 'TR ' + v for k, v in m.CATALOGS['en'].items()}
        for item in m.ITEMS:
            turkish[item['id']] = 'Kontrol ' + item['id']
        broken = dict(turkish, aspect_pass='Oran uygun.')
        with self.assertRaisesRegex(ValueError, 'placeholders'):
            self.prepare([(1280, 720)], context, language='tr', labels=broken)
        with self.assertRaisesRegex(ValueError, 'built-in labels'):
            self.prepare([(1280, 720)], context, language='pt', labels=turkish)
        run, _ = self.prepare([(1280, 720)], context, language='tr', labels=dict(turkish, report_title='Kapak *incelemesi*'), name='tr')
        self.review(run, 'A')
        report = self.report(run)
        self.assertIn('# Kapak &#42;incelemesi&#42;', report)
        self.assertIn('| Kontrol topic_match |', report)


class PreRoundCases(unittest.TestCase):
    """Pre test thread 33a4dd88 on the 1.0.52 candidate (review-thumbnail 0.1.6)."""

    setUp = ProductionCases.setUp
    prepare = ProductionCases.prepare
    report = ProductionCases.report

    def fill(self, run, template, capture='original', visible=(), ui=()):
        """Fill the prepare template the way a host would: replace every placeholder, keep the shape."""
        review = json.loads(json.dumps(template))
        for c in review['candidates']:
            c['observations'] = dict(capture=capture, visible_text=list(visible), ui_text=list(ui), main_subject='一位歌手在复古画面里。', disclosures=[])
            c['items'] = {i['id']: dict(verdict='pass', reason='画面清楚。', fix='', basis='observed') for i in m.ITEMS}
            c.update(priorities=[], suitable=True, suitability_reason='主题清楚，可以直接用。')
        if review['title_review']:
            review['title_review']['clarity'] = dict(verdict='pass', reason='歌名和版本都清楚。', fix='')
            for row in review['title_review']['pairing']:
                row.update(verdict='pass', reason='封面展示了标题说的歌手。', fix='')
        for row in review['comparisons']:
            row.update(winner=row['pair'][0], reason='前者焦点更清楚，后者文字更多。')
        review['recommendation'] = dict(candidate_id='A', reason='焦点最清楚。')
        m.write(run / 'review.json', review)
        return review

    # Issue 1: cover text that also appears in the list card (an artist name) was rejected twice.
    def test_cover_text_may_also_appear_in_the_interface(self):
        run, prepared = self.prepare([(749, 407)], {'title': 'Rick Astley - Never Gonna Give You Up (Official Music Video)'}, language='zh-CN')
        ui = ['Rick Astley - Never Gonna Give You Up (Official Music Video)', 'Rick Astley', '3:33', '16亿次观看']
        review = self.fill(run, prepared['review_template'], capture='screenshot', visible=['RICK ASTLEY', 'NEVER GONNA GIVE YOU UP', '4K'], ui=ui)
        review['candidates'][0]['items']['eye_catching']['reason'] = '大字“RICK ASTLEY”在小尺寸下也能读出。'
        m.write(run / 'review.json', review)
        report = self.report(run)
        self.assertIn('图中文字：RICK ASTLEY、NEVER GONNA GIVE YOU UP、4K', report)
        self.assertIn('> 这是截图（749×407），封面四周带有平台界面，所以比例不判。请发原图文件', report)
        self.assertIn('| 分辨率与比例 | 待确认 |', report)

    # Issue 2: an unknown target format is "to confirm", not a failure and not a first change.
    def test_unknown_format_is_not_a_failure(self):
        title = 'Never Gonna Give You Up 官方MV 4K修复版'
        run, prepared = self.prepare([(1280, 720)], {'title': title}, language='zh-CN')
        self.assertEqual('no_target', prepared['measurements'][0]['status'])
        review = self.fill(run, prepared['review_template'], visible=['RICK ASTLEY', '4K'])
        review['candidates'][0]['items']['resolution_aspect'].update(verdict='fail', reason='没有给出目标格式。', fix='告诉我平台。', basis='missing_context')
        review['candidates'][0]['priorities'] = ['resolution_aspect']
        m.write(run / 'review.json', review)
        with self.assertRaisesRegex(ValueError, 'not a missing-context failure'):
            m.deliver(run)
        self.fill(run, prepared['review_template'], visible=['RICK ASTLEY', '4K'])
        report = self.report(run)
        self.assertIn('| 分辨率与比例 | 待确认 | 画面清楚。 脚本实测：1280×720（1.778:1）。没有给出目标格式，比例暂不判断', report)
        self.assertIn('没有必须修改的项。', report)
        self.assertNotIn('| 分辨率与比例 | 不过 |', report)
        self.assertIn('## 推荐\n\nA\n', report)

    # Issue 3: the first review.json was rejected for wrong fields; prepare now returns the exact shape.
    def test_prepare_template_has_the_exact_shape(self):
        run, prepared = self.prepare([(1280, 720), (1280, 721)], {'title': 'T', 'target_aspect_ratio': '16:9', 'target_aspect_source': 'user'}, language='en')
        template = prepared['review_template']
        self.assertEqual(template, json.loads((run / 'review.template.json').read_text()))
        self.assertEqual(m.digest((run / 'request.json').read_bytes()), template['request_sha256'])
        self.assertEqual(['candidate_id', 'reason'], list(template['recommendation']))
        self.assertEqual([['A', 'B']], [row['pair'] for row in template['comparisons']])
        self.assertEqual(['A', 'B'], [row['candidate_id'] for row in template['title_review']['pairing']])
        with self.assertRaises(ValueError):
            m.write(run / 'review.json', template)
            m.deliver(run)
        review = self.fill(run, template)
        review['recommendation'] = {'candidate': 'A', 'reason': 'Clearest focus.'}
        m.write(run / 'review.json', review)
        with self.assertRaisesRegex(ValueError, r"recommendation: missing fields \['candidate_id'\], unexpected fields \['candidate'\]"):
            m.deliver(run)
        self.fill(run, template)
        m.deliver(run)

if __name__=='__main__':unittest.main()
