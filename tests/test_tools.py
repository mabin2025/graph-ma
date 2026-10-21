"""Observable invariants for service, agent and saved Notebook workflows."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from analysis import changes, check_shape, fingerprint, inventory, save_json
from extract_notebook_outputs import extract
from validate import validate

FIXTURES = Path(__file__).parent / 'fixtures'
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><title>Chain</title><desc>Test chain</desc><defs><marker id="end"/></defs><path marker-end="url(#end)"/></svg>'


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(FIXTURES, self.root / 'src')
        self.docs = self.root / 'docs'
        self.docs.mkdir()
        (self.docs / 'assets').mkdir()
        (self.docs / 'assets' / 'main.svg').write_text(SVG, encoding='utf-8')
        self.doc = self.docs / 'review.md'
        self.doc.write_text('![main](assets/main.svg)\n', encoding='utf-8')
        self.manifest = self.docs / 'analysis.json'
        self.data = {
            'version': 1, 'scope': {'paths': ['src'], 'exclude': []},
            'modules': [
                {'id': 'service', 'sources': ['src/service/app.py'], 'sections': ['请求链路'], 'assets': ['assets/main.svg']},
                {'id': 'agent', 'sources': ['src/agent/router.py'], 'depends_on': ['service'], 'sections': ['工具执行']},
                {'id': 'notebook', 'sources': ['src/notebook/demo.ipynb'], 'sections': ['实验结果']}
            ],
            'claims': [
                {'id': 'missing-item', 'module': 'service', 'kind': 'source', 'text': 'Missing keys return status 404', 'evidence': [{'path': 'src/service/app.py', 'lines': [8, 10]}]},
                {'id': 'bounded-loop', 'module': 'agent', 'kind': 'source', 'text': 'A step limit ends the tool branch', 'evidence': [{'path': 'src/agent/router.py', 'lines': [5, 8]}]},
                {'id': 'saved-output', 'module': 'notebook', 'kind': 'historical', 'text': 'Saved fixture SVG', 'evidence': [{'path': 'src/notebook/demo.ipynb', 'cell': 2, 'cell_id': 'saved-figure', 'lines': [1, 2]}]}
            ]
        }
        self.data['revision'] = {'git_commit': None, 'files': inventory(self.root, self.data['scope'])}
        save_json(self.manifest, self.data)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        save_json(self.manifest, self.data)

    def notebook(self):
        return self.root / 'src/notebook/demo.ipynb'

    def test_valid_document_and_source_locations(self):
        result = validate(self.doc, self.manifest, self.root, [self.docs / 'assets/main.svg'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['warnings'], [])

    def test_missing_image_and_dangling_svg_reference(self):
        self.doc.write_text('![x](missing.png)\n![y](assets/main.svg)', encoding='utf-8')
        (self.docs / 'assets/main.svg').write_text(SVG.replace('id="end"', 'id="other"'), encoding='utf-8')
        errors = validate(self.doc)['errors']
        self.assertTrue(any('Missing image' in x for x in errors))
        self.assertTrue(any('#end' in x for x in errors))

    def test_obsidian_reference_encoded_paths_and_code_examples(self):
        shutil.copyfile(self.docs / 'assets/main.svg', self.docs / 'assets/a b.svg')
        self.doc.write_text('![[assets/a b.svg|400]]\n![x][figure]\n[figure]: assets/a%20b.svg\n```md\n![example](not-real.png)\n```\n', encoding='utf-8')
        self.assertEqual(validate(self.doc)['errors'], [])

    def test_missing_reference_and_malformed_xml(self):
        self.doc.write_text('![x][absent]\n![y](assets/main.svg)', encoding='utf-8')
        (self.docs / 'assets/main.svg').write_text('<svg>', encoding='utf-8')
        self.assertEqual(len(validate(self.doc)['errors']), 2)

    def test_preserved_historical_svg_need_not_have_diagram_descriptions(self):
        path = self.docs / 'assets/main.svg'
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding='utf-8')
        self.assertEqual(validate(self.doc)['errors'], [])
        self.assertEqual(len(validate(flowcharts=[path])['errors']), 2)

    def test_source_range_and_cell_identity_are_checked(self):
        self.data['claims'][0]['evidence'][0]['lines'] = [8, 1000]
        self.data['claims'][2]['evidence'][0]['cell_id'] = 'moved'
        self.write()
        errors = validate(analysis_path=self.manifest, project=self.root)['errors']
        self.assertTrue(any('line range' in x for x in errors))
        self.assertTrue(any('cell_id' in x for x in errors))

    def test_binary_historical_evidence_does_not_require_text_decoding(self):
        path = self.root / 'src/result.png'
        path.write_bytes(b'\x89PNG\r\n\x1a\n\xff')
        self.data['claims'][2]['evidence'] = [{'path': 'src/result.png'}]
        self.write()
        self.assertEqual(validate(analysis_path=self.manifest, project=self.root)['errors'], [])

    def test_excluded_files_do_not_create_source_drift(self):
        self.data['scope']['exclude'] = ['src/cache/*']
        (self.root / 'src/cache').mkdir()
        (self.root / 'src/cache/large.bin').write_bytes(b'ignored')
        self.assertEqual(changes(self.data, self.root)['changed_files'], [])

    def test_duplicate_ids_unknown_dependencies_and_ungrounded_claims_fail(self):
        for edit in [lambda d: d['modules'].append(copy.deepcopy(d['modules'][0])),
                     lambda d: d['modules'][0].update(depends_on=['unknown']),
                     lambda d: d['claims'][0].update(evidence=[])]:
            data = copy.deepcopy(self.data)
            edit(data)
            with self.assertRaises(ValueError):
                check_shape(data)

    def test_evidence_path_cannot_escape_project(self):
        self.data['claims'][0]['evidence'][0]['path'] = '../outside.txt'
        self.write()
        with self.assertRaises(ValueError):
            validate(analysis_path=self.manifest, project=self.root)

    def test_no_source_change_does_not_rewrite_files(self):
        original = self.manifest.read_bytes()
        self.assertEqual(changes(self.data, self.root)['changed_files'], [])
        self.assertEqual(self.manifest.read_bytes(), original)

    def test_modified_source_propagates_to_dependent_documentation(self):
        path = self.root / 'src/service/app.py'
        path.write_text(path.read_text(encoding='utf-8').replace('404', '410'), encoding='utf-8')
        result = changes(self.data, self.root)
        self.assertEqual(result['affected_modules'], ['agent', 'service'])
        self.assertEqual(set(result['affected_claims']), {'missing-item', 'bounded-loop'})
        self.assertIn('assets/main.svg', result['assets'])
        self.assertEqual(result['unmapped_changes'], [])

    def test_new_unmapped_file_requires_scope_review(self):
        (self.root / 'src/config.json').write_text('{}', encoding='utf-8')
        result = changes(self.data, self.root)
        self.assertEqual(result['unmapped_changes'], ['src/config.json'])
        self.assertEqual(len(result['affected_modules']), 3)

    def test_deleted_source_keeps_affected_module_visible(self):
        (self.root / 'src/service/app.py').unlink()
        result = changes(self.data, self.root)
        self.assertEqual(result['changed_files'][0]['status'], 'deleted')
        self.assertIn('service', result['affected_modules'])
        self.assertTrue(validate(analysis_path=self.manifest, project=self.root)['errors'])

    def test_cyclic_dependencies_produce_a_finite_impact_report(self):
        self.data['modules'][0]['depends_on'] = ['agent']
        (self.root / 'src/agent/router.py').write_text('changed', encoding='utf-8')
        self.assertEqual(changes(self.data, self.root)['affected_modules'], ['agent', 'service'])

    def test_missing_baseline_cannot_claim_no_changes(self):
        del self.data['revision']
        with self.assertRaises(ValueError):
            changes(self.data, self.root)

    def test_cli_snapshot_refuses_to_fingerprint_its_own_generated_record(self):
        self.data['scope']['paths'] = ['.']
        self.write()
        before = self.manifest.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPTS / 'analysis.py'), 'snapshot', '--analysis', str(self.manifest), '--project', str(self.root)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(before, self.manifest.read_bytes())

    def test_notebook_code_and_output_drift_are_distinguished(self):
        path = self.notebook()
        original = json.loads(path.read_text(encoding='utf-8'))
        for field, code_changed, outputs_changed in [('source', True, False), ('outputs', False, True)]:
            data = copy.deepcopy(original)
            data['cells'][1][field] = ['changed'] if field == 'source' else []
            path.write_text(json.dumps(data), encoding='utf-8')
            item = changes(self.data, self.root)['changed_files'][0]
            self.assertEqual(item['code_changed'], code_changed)
            self.assertEqual(item['outputs_changed'], outputs_changed)

    def test_extract_records_file_position_and_historical_provenance(self):
        result = extract(self.notebook(), self.docs / 'results', [2])
        self.assertEqual(result[0]['cell'], 2)
        self.assertEqual(result[0]['cell_id'], 'saved-figure')
        self.assertEqual(result[0]['kind'], 'historical')
        self.assertEqual(result[0]['notebook_sha256'], fingerprint(self.notebook())['sha256'])
        self.assertTrue((self.docs / 'results' / result[0]['asset']).is_file())

    def test_extract_never_overwrites_and_execution_count_is_not_position(self):
        target = self.docs / 'results'
        extract(self.notebook(), target, [2])
        before = {p.name: p.read_bytes() for p in target.iterdir()}
        with self.assertRaises(ValueError):
            extract(self.notebook(), target, [2])
        self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})
        with self.assertRaises(ValueError):
            extract(self.notebook(), self.docs / 'other', [42])

    def test_extract_invalid_payload_writes_no_assets(self):
        path = self.notebook()
        data = json.loads(path.read_text(encoding='utf-8'))
        data['cells'][1]['outputs'][0]['data'] = {'image/png': 'not valid base64'}
        path.write_text(json.dumps(data), encoding='utf-8')
        target = self.docs / 'invalid'
        with self.assertRaises(ValueError):
            extract(path, target, [2])
        self.assertFalse(target.exists())

    def test_empty_image_selection_creates_no_output_directory(self):
        target = self.docs / 'empty'
        with self.assertRaises(ValueError):
            extract(self.notebook(), target, [1])
        self.assertFalse(target.exists())

    def test_concurrent_manifest_change_is_preserved(self):
        original = self.manifest.read_bytes()
        self.manifest.write_text('{"user":"new content"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            save_json(self.manifest, self.data, expected=original)
        self.assertEqual(json.loads(self.manifest.read_text(encoding='utf-8')), {'user': 'new content'})

    def test_cli_exit_codes_snapshot_and_out_of_scope_changes(self):
        def run(*args):
            return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding='utf-8')
        valid = run(SCRIPTS / 'validate.py', '--document', self.doc)
        self.assertEqual(valid.returncode, 0, valid.stdout)
        self.doc.write_text('![x](absent.png)', encoding='utf-8')
        self.assertEqual(run(SCRIPTS / 'validate.py', '--document', self.doc).returncode, 1)
        self.assertEqual(run(SCRIPTS / 'analysis.py', 'snapshot', '--analysis', self.manifest, '--project', self.root).returncode, 0)
        self.doc.write_text('user edit', encoding='utf-8')
        result = run(SCRIPTS / 'analysis.py', 'changes', '--analysis', self.manifest, '--project', self.root)
        self.assertEqual(json.loads(result.stdout)['changed_files'], [])


if __name__ == '__main__':
    unittest.main()
