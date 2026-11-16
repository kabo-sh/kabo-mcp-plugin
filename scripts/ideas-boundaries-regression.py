"""Verify that valid follow-up chat/count/language are not wrongly blocked, and that failed artifacts cannot be delivered."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('counts', ROOT/'scripts/ideas-count-regression.py')
counts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(counts)
import report_language as locale


class Boundaries(unittest.TestCase):
    setUp = counts.IdeaCounts.setUp
    write = counts.IdeaCounts.write
    stage = counts.IdeaCounts.stage
    intent = counts.IdeaCounts.intent
    output = counts.IdeaCounts.output

    def test_spanish_regions_deliver_without_authored_interface_translations(self):
        """Spanish/region labels throughout the whole flow, no 92-entry UI mapping, and the opening and filming approach kept per item."""
        for tag in ('es', 'es-MX', 'español'):
            with self.subTest(tag=tag):
                run = self.root/tag
                intent = self.intent(5)
                intent['report_language'] = tag
                self.write(run, 'intent.json', intent)
                self.assertEqual('ok', self.stage(run, 'prep', '--intent', run/'intent.json')[1]['status'])
                output = self.output(5)
                output['report_language'] = 'es-MX' if tag == 'es-MX' else 'es'
                output['evidence_gap_translations'] = []
                output['overview'].update(headline='Ideas para grabar', portfolio_logic='Opciones concretas', missing_context_effect='Sin datos externos')
                for i, item in enumerate(output['ideas'], 1):
                    item.update(working_title=f'Idea de grabación {i}', making_direction=f'Graba el proceso {i} paso a paso.', why_for_creator='Se ajusta al tema aportado.')
                    item['hook_preview']['opening_line'] = f'Mira cómo cambia el resultado {i}.'
                self.write(run, 'idea_set.json', output)
                self.assertEqual('ok', self.stage(run, 'core')[1]['status'])
                r = subprocess.run([sys.executable, '-B', str(counts.SKILL/'scripts/deliver_ideas.py'), '--run-dir', str(run)], capture_output=True, text=True)
                self.assertEqual(0, r.returncode, r.stdout)
                report = Path(json.loads(r.stdout)['report_path']).read_text()
                self.assertIn('## Opciones', report)
                self.assertIn('Estado: `lista para elegir`', report)
                self.assertEqual(5, report.count('**Frase inicial:**'))
                self.assertEqual(5, report.count('**Cómo grabarlo:**'))
                for item in output['ideas']:
                    self.assertIn(item['hook_preview']['opening_line'], report)
                    self.assertIn(item['making_direction'], report)

    def test_fixed_ui_cannot_be_replaced_by_authored_prose(self):
        """Old translations stay readable, and the fixed UI is not overridden by another language supplied by the model."""
        data = self.output(3)
        data['report_language'] = 'es'
        data['evidence_gap_translations'] = [{'source_text':'ready_for_selection','report_text':'READY IN ENGLISH'}]
        self.assertEqual('lista para elegir', locale.report_value_translations(data)['ready_for_selection'])
        self.assertEqual(set(), locale.ui_label_sources(data))

    def test_gap_named_like_fixed_enum_still_needs_its_own_translation(self):
        """When an evidence gap has the same name as an enum, do not automatically fabricate a meaning for the gap."""
        data = self.output(3)
        data['report_language'] = 'es'
        data['evidence_summary']['data_gaps'] = ['low']
        data['evidence_gap_translations'] = []
        with self.assertRaisesRegex(ValueError, 'every original gap'):
            locale.evidence_gaps(data)
        data['evidence_gap_translations'] = [{'source_text':'low','report_text':'Faltan datos: low'}]
        self.assertEqual(['Faltan datos: low'], locale.evidence_gaps(data))

    def test_fixed_catalog_complete_and_preserves_format(self):
        """Translate all fixed UI; do not miss status/boundary copy."""
        self.assertEqual({v['en'] for v in locale.CATALOG.values()}, set(locale.SPANISH))
        for entry in locale.CATALOG.values():
            self.assertTrue(entry['es'].strip())
            self.assertEqual(entry['en'].endswith(' '), entry['es'].endswith(' '))
        self.assertEqual('en', locale.report_language({'report_language':'English'}))
        self.assertEqual('es', locale.report_language({'report_language':'Spanish'}))
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            locale.report_language({'report_language':'es--MX'})

    def test_unknown_locale_does_not_silently_become_english(self):
        """An unknown vocabulary still needs an explicit translation, and a deterministic mapping must not let a wrong language through."""
        data = self.output(3)
        data['report_language'] = 'de-DE'
        data['evidence_gap_translations'] = []
        with self.assertRaisesRegex(ValueError, 'Missing UI label translations'):
            locale.presentation_translations(data)

    def test_region_change_is_not_ignored(self):
        """Sharing a language does not mean the user's explicit region requirement can be ignored."""
        intent = self.intent(3);intent['report_language'] = 'es-MX'
        self.write(self.root, 'intent.json', intent)
        self.assertEqual('ok', self.stage(self.root, 'prep', '--intent', self.root/'intent.json')[1]['status'])
        output = self.output(3);output['report_language'] = 'es-ES';output['evidence_gap_translations'] = []
        self.write(self.root, 'idea_set.json', output)
        result = self.stage(self.root, 'core')[1]
        self.assertEqual('needs_revision', result['status'])
        self.assertIn('report_language mismatch', '\n'.join(result['errors']))
        self.assertFalse((self.root/'FINAL_IDEAS.md').exists())


if __name__ == '__main__':
    unittest.main()
