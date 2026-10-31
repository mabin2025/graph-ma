"""Graph interoperability, bounded navigation and project-scoped freshness."""
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
from ua_graph import check_graph, freshness, query_graph


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src/app.py').write_text('def handle():\n    return 1\n', encoding='utf-8')
        (self.root / 'src/tool.py').write_text('def execute():\n    return 2\n', encoding='utf-8')
        self.path = self.root / 'knowledge-graph.json'
        self.graph = {
            'version': '1.0.0', 'kind': 'codebase',
            'project': {'name': 'sample', 'description': 'Scoped example', 'languages': ['Python'],
                        'frameworks': [], 'analyzedAt': '2026-10-31T00:00:00Z', 'gitCommitHash': ''},
            'nodes': [
                {'id': 'file:src/app.py', 'type': 'file', 'name': 'app.py', 'filePath': 'src/app.py',
                 'summary': '请求入口', 'tags': ['entry'], 'complexity': 'simple'},
                {'id': 'function:src/app.py:handle', 'type': 'function', 'name': 'handle', 'filePath': 'src/app.py',
                 'lineRange': [1, 2], 'summary': '处理请求', 'tags': ['handler'], 'complexity': 'simple'},
                {'id': 'file:src/tool.py', 'type': 'file', 'name': 'tool.py', 'filePath': 'src/tool.py',
                 'summary': '工具执行', 'tags': ['tool'], 'complexity': 'simple'},
            ],
            'edges': [
                {'source': 'file:src/app.py', 'target': 'function:src/app.py:handle',
                 'type': 'contains', 'direction': 'forward', 'weight': 1.0},
                {'source': 'file:src/app.py', 'target': 'file:src/tool.py',
                 'type': 'depends_on', 'direction': 'forward', 'weight': 0.6},
            ],
            'layers': [{'id': 'entry', 'name': '入口', 'description': '请求边界', 'nodeIds': ['file:src/app.py']}],
            'tour': [{'order': 1, 'title': '先看入口', 'description': '理解输入输出', 'nodeIds': ['file:src/app.py']}],
        }
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.graph, ensure_ascii=False), encoding='utf-8')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / 'ua_graph.py'), *map(str, args),
                               '--graph', str(self.path), '--project', str(self.root)],
                              capture_output=True, text=True, encoding='utf-8')

    def test_source_checks_and_read_only_cli(self):
        before = self.path.read_bytes()
        result = self.run_cli('check')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)['nodes_checked'], 3)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(json.loads(result.stdout)['freshness']['state'], 'unknown')

    def test_missing_source_is_detected_but_old_graph_remains_searchable(self):
        (self.root / 'src/tool.py').unlink()
        self.assertEqual(self.run_cli('check').returncode, 1)
        result = self.run_cli('query', '--query', '工具')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('file:src/tool.py', [n['id'] for n in json.loads(result.stdout)['subgraph']['nodes']])

    def test_unknown_endpoints_and_duplicate_ids_are_rejected(self):
        for mutation in ('duplicate', 'edge', 'layer', 'tour'):
            graph = copy.deepcopy(self.graph)
            if mutation == 'duplicate':
                graph['nodes'].append(graph['nodes'][0])
            elif mutation == 'edge':
                graph['edges'][0]['target'] = 'missing'
            else:
                graph['layers' if mutation == 'layer' else 'tour'][0]['nodeIds'] = ['missing']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                check_graph(graph, self.root)

    def test_source_traversal_and_invalid_lines_are_rejected(self):
        for value in ('../outside.py', 'C:/outside.py'):
            graph = copy.deepcopy(self.graph)
            graph['nodes'][0]['filePath'] = value
            with self.subTest(path=value), self.assertRaises(ValueError):
                check_graph(graph, self.root)
        self.graph['nodes'][1]['lineRange'] = [1, 300]
        with self.assertRaises(ValueError):
            check_graph(self.graph, self.root)

    def test_query_preserves_relationships_and_filters_group_references(self):
        result = query_graph(self.graph, ['APP.PY'], hops=1, limit=3)
        self.assertEqual(len(result['nodes']), 3)
        self.assertEqual(len(result['edges']), 2)
        self.assertEqual(result['layers'][0]['nodeIds'], ['file:src/app.py'])
        isolated = query_graph(self.graph, ['工具'], hops=0)
        self.assertEqual(len(isolated['nodes']), 1)
        self.assertEqual(isolated['edges'], [])
        self.assertEqual(isolated['tour'], [])
        self.assertEqual(query_graph(self.graph, ['nonexistent'])['nodes'], [])

    def test_hub_query_obeys_limit_and_reports_truncated_edges(self):
        self.graph['edges'] *= 10
        result = query_graph(self.graph, ['app.py'], hops=2, limit=2)
        self.assertEqual(len(result['nodes']), 2)
        self.assertLessEqual(len(result['edges']), 8)
        self.assertGreater(result['omitted_edges'], 0)
        invalid = self.run_cli('query', '--query', 'app', '--limit', '0')
        self.assertEqual(invalid.returncode, 1)

    def test_analysis_links_and_fingerprints_are_checked(self):
        from analysis import inventory
        manifest = self.root / 'analysis.json'
        data = {'version': 1, 'scope': {'paths': ['src']},
                'modules': [{'id': 'app', 'sources': ['src/app.py'], 'graph_node_ids': ['file:src/app.py']}],
                'claims': [], 'revision': {'git_commit': None, 'files': inventory(self.root, {'paths': ['src']})}}
        manifest.write_text(json.dumps(data), encoding='utf-8')
        (self.root / 'src/app.py').write_text('def handle():\n    return 3\n', encoding='utf-8')
        result = self.run_cli('check', '--analysis', manifest)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)['analysis_changes']['affected_modules'], ['app'])
        data['modules'][0]['graph_node_ids'] = ['missing']
        manifest.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.run_cli('check', '--analysis', manifest).returncode, 1)


@unittest.skipUnless(shutil.which('git'), 'Git unavailable')
class FreshnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.project = self.repo / 'project'
        self.project.mkdir()
        (self.project / 'app.py').write_text('return_value = 1\n', encoding='utf-8')
        (self.repo / 'sibling.txt').write_text('old', encoding='utf-8')
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Graph Test')
        self.git('add', '.')
        self.git('commit', '-qm', 'initial')
        self.graph = {'project': {'gitCommitHash': self.git('rev-parse', 'HEAD').strip()}}
        self.path = self.project / 'knowledge-graph.json'
        self.path.write_text('{}', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL).decode()

    def test_sibling_commit_and_generated_graph_do_not_imply_source_drift(self):
        (self.repo / 'sibling.txt').write_text('new', encoding='utf-8')
        self.git('add', 'sibling.txt')
        self.git('commit', '-qm', 'sibling only')
        result = freshness(self.graph, self.project, self.path)
        self.assertEqual(result['state'], 'no_detected_changes', result)

    def test_same_commit_detects_staged_unstaged_and_untracked_source(self):
        (self.project / 'app.py').write_text('return_value = 2\n', encoding='utf-8')
        (self.project / 'staged.py').write_text('new = True', encoding='utf-8')
        self.git('add', 'project/staged.py')
        (self.project / 'new.py').write_text('new = True', encoding='utf-8')
        (self.project / '.ua').mkdir()
        (self.project / '.ua/knowledge-graph.json').write_text('{}', encoding='utf-8')
        result = freshness(self.graph, self.project, self.path)
        self.assertEqual(result['state'], 'changed', result)
        self.assertEqual(result['files']['staged'], ['staged.py'])
        self.assertEqual(result['files']['unstaged'], ['app.py'])
        self.assertEqual(result['files']['untracked'], ['new.py'])

    def test_invalid_commit_remains_unknown_without_executing_metadata(self):
        self.graph['project']['gitCommitHash'] = '--help; echo unexpected'
        result = freshness(self.graph, self.project, self.path)
        self.assertEqual(result['state'], 'unknown', result)
        self.assertIsNone(result['graph_commit'])


if __name__ == '__main__':
    unittest.main()
