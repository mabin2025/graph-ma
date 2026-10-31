"""Installation side effects are confined to isolated directories; no network."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import install as installer


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        for name in ('SKILL.md', 'README.md'):
            (self.source / name).write_text(name, encoding='utf-8')
        for name in ('agents', 'references', 'scripts'):
            (self.source / name).mkdir()
            (self.source / name / 'sample.txt').write_text(name, encoding='utf-8')
        self.skills = self.root / 'custom skills'
        self.repo = self.root / 'ua repo'
        self.plugin = self.repo / 'understand-anything-plugin'
        self.alias = self.root / 'plugin-link'

    def tearDown(self):
        # Unlink our own junctions before TemporaryDirectory performs cleanup.
        for parent in (self.skills, self.root, self.skills / '.graph-ma-backups'):
            if parent.is_dir():
                for path in parent.iterdir():
                    if installer.is_link(path):
                        self.assertTrue(path.parent.resolve().is_relative_to(self.root.resolve()))
                        if os.name == 'nt' and not path.is_symlink():
                            os.rmdir(path)
                        else:
                            path.unlink()
        self.tmp.cleanup()

    def make_ua(self):
        (self.plugin / 'skills/understand').mkdir(parents=True)
        (self.plugin / 'skills/understand/SKILL.md').write_text('upstream skill', encoding='utf-8')
        (self.repo / 'package.json').write_text('{}', encoding='utf-8')
        return self.plugin

    def install(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return installer.install(self.source, self.skills, self.repo, plugin_link=self.alias, **kwargs)

    def test_skip_ua_copies_complete_skill_without_dependency_work(self):
        with patch.object(installer, 'ensure_ua') as ensure:
            destination = self.install(skip_ua=True)
        ensure.assert_not_called()
        for rel in installer.resource_files(self.source):
            self.assertEqual((destination / rel).read_bytes(), (self.source / rel).read_bytes())
        self.assertFalse(self.repo.exists())
        self.assertFalse(self.alias.exists())

    def test_default_installs_ua_entries_and_a_valid_locator(self):
        plugin = self.make_ua()
        with patch.object(installer, 'ensure_ua', return_value=plugin) as ensure:
            destination = self.install()
        ensure.assert_called_once_with(self.repo)
        self.assertTrue(installer.same_directory(self.skills / 'understand', plugin / 'skills/understand'))
        self.assertTrue(installer.same_directory(self.alias, plugin))
        metadata = json.loads((destination / 'ua-runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(Path(metadata['plugin_root']), plugin)

    def test_repeat_install_keeps_current_files_and_links_without_backups(self):
        plugin = self.make_ua()
        with patch.object(installer, 'ensure_ua', return_value=plugin):
            destination = self.install()
            stamp = (destination / 'SKILL.md').stat().st_mtime_ns
            self.install()
        self.assertEqual((destination / 'SKILL.md').stat().st_mtime_ns, stamp)
        self.assertFalse((self.skills / '.graph-ma-backups').exists())

    def test_conflicting_skill_is_preserved_before_network_work(self):
        destination = self.install(skip_ua=True)
        (destination / 'SKILL.md').write_text('user changes', encoding='utf-8')
        with patch.object(installer, 'ensure_ua') as ensure, self.assertRaises(ValueError):
            self.install()
        ensure.assert_not_called()
        self.assertEqual((destination / 'SKILL.md').read_text(encoding='utf-8'), 'user changes')

    def test_replace_preserves_original_files_in_a_backup(self):
        destination = self.install(skip_ua=True)
        (destination / 'SKILL.md').write_text('user changes', encoding='utf-8')
        self.install(skip_ua=True, replace=True)
        backups = list((self.skills / '.graph-ma-backups').glob('graph-ma-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'SKILL.md').read_text(encoding='utf-8'), 'user changes')
        self.assertEqual((destination / 'SKILL.md').read_text(encoding='utf-8'), 'SKILL.md')

    def test_conflicting_ua_skill_aborts_before_installing_graphma(self):
        plugin = self.make_ua()
        (self.skills / 'understand').mkdir(parents=True)
        (self.skills / 'understand/local.txt').write_text('preserve', encoding='utf-8')
        with patch.object(installer, 'ensure_ua', return_value=plugin), self.assertRaises(ValueError):
            self.install()
        self.assertFalse((self.skills / 'graph-ma').exists())
        self.assertEqual((self.skills / 'understand/local.txt').read_text(), 'preserve')

    def test_unmanaged_runtime_locator_is_preserved_before_linking(self):
        plugin = self.make_ua()
        destination = self.install(skip_ua=True)
        locator = destination / 'ua-runtime.json'
        locator.write_text('{"plugin_root":"user-selected"}', encoding='utf-8')
        with patch.object(installer, 'ensure_ua', return_value=plugin), self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.alias.exists())
        self.assertFalse((self.skills / 'understand').exists())
        self.assertEqual(json.loads(locator.read_text())['plugin_root'], 'user-selected')

    def test_failed_link_restores_the_original_directory(self):
        plugin = self.make_ua()
        (self.skills / 'understand').mkdir(parents=True)
        original = self.skills / 'understand/local.txt'
        original.write_text('preserve', encoding='utf-8')
        # Test the replace/rollback operation independently of the plugin alias.
        with patch.object(installer, 'link_directory', side_effect=OSError('link failed')):
            with self.assertRaises(OSError):
                installer.install_link(plugin / 'skills/understand', self.skills / 'understand', self.skills)
        self.assertEqual(original.read_text(), 'preserve')

    def test_missing_prerequisite_does_not_publish_a_skill(self):
        with patch.object(installer, 'need_command', side_effect=ValueError('node missing')):
            with self.assertRaises(ValueError):
                self.install()
        self.assertFalse(self.skills.exists())
        self.assertFalse(self.repo.exists())

    def test_existing_runtime_is_reused_without_pulling_or_building(self):
        plugin = self.make_ua()
        with patch.object(installer, 'need_command', return_value='node'), \
             patch.object(installer, 'core_ready', return_value=True), patch.object(installer, 'run') as run:
            self.assertEqual(installer.ensure_ua(self.repo), plugin)
        run.assert_not_called()

    def test_unbuilt_runtime_installs_locked_dependencies_and_builds_core(self):
        self.make_ua()
        with patch.object(installer, 'need_command', side_effect=lambda name, minimum=None: name), \
             patch.object(installer, 'core_ready', side_effect=[False, True]), patch.object(installer, 'run') as run:
            installer.ensure_ua(self.repo)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands, [['pnpm', 'install', '--frozen-lockfile'],
                                    ['pnpm', '--filter', '@understand-anything/core', 'build']])

    def test_unrelated_ua_directory_and_nested_install_destination_are_preserved(self):
        self.repo.mkdir()
        marker = self.repo / 'unrelated.txt'
        marker.write_text('preserve', encoding='utf-8')
        with patch.object(installer, 'need_command', return_value='node'), self.assertRaises(ValueError):
            installer.ensure_ua(self.repo)
        self.assertEqual(marker.read_text(), 'preserve')
        with self.assertRaises(ValueError):
            installer.install(self.source, self.source / 'scripts/skills', self.repo, skip_ua=True)

    def test_python_entry_point_can_install_to_a_directory_with_spaces(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'install.py'), '--skip-ua',
                                 '--skills-dir', str(self.skills), '--ua-dir', str(self.repo)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.skills / 'graph-ma/scripts/ua_graph.py').is_file())
        self.assertFalse(self.repo.exists())


if __name__ == '__main__':
    unittest.main()
