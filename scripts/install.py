#!/usr/bin/env python3
"""Install graph-ma and, by default, a working Understand Anything environment."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

SKILL_ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ('SKILL.md', 'README.md', 'agents', 'references', 'scripts')
UA_REPOSITORY = 'https://github.com/Egonex-AI/Understand-Anything.git'
CORE_PROBE = """
import {pathToFileURL} from 'node:url';
const core = await import(pathToFileURL(process.argv[1]).href);
for (const name of ['TreeSitterPlugin', 'PluginRegistry', 'createIgnoreFilter']) {
  if (typeof core[name] !== 'function') throw new Error('Missing UA export: ' + name);
}
const parser = new core.TreeSitterPlugin(core.builtinLanguageConfigs.filter(c => c.treeSitter));
await parser.init();
"""


def run(args, **kwargs):
    print('-> ' + ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def need_command(name, minimum=None):
    command = shutil.which(name)
    if not command:
        raise ValueError(f'{name} is required. Install it, or use --skip-ua for graph-ma alone.')
    if minimum is not None:
        result = run([command, '--version'], capture_output=True, text=True)
        match = re.search(r'\d+', result.stdout)
        if not match or int(match.group()) < minimum:
            raise ValueError(f'{name} >= {minimum} is required; found {result.stdout.strip()}')
    return command


def core_ready(node, plugin):
    entry = plugin / 'packages/core/dist/index.js'
    if not entry.is_file():
        return False
    result = subprocess.run([str(node), '--input-type=module', '-e', CORE_PROBE, str(entry)],
                            capture_output=True, text=True)
    if result.returncode:
        print('UA runtime needs a build: ' + result.stderr[-1200:], file=sys.stderr)
    return result.returncode == 0


def ensure_ua(repo):
    """Reuse an existing checkout without pulling or resetting local changes."""
    node = need_command('node', 22)
    plugin = repo / 'understand-anything-plugin'
    if repo.exists():
        if not (plugin / 'skills/understand/SKILL.md').is_file() or not (repo / 'package.json').is_file():
            raise ValueError(f'{repo} exists but is not a complete UA checkout; choose another --ua-dir.')
    else:
        git = need_command('git')
        # Check build prerequisites before downloading a new checkout.
        need_command('pnpm', 10)
        repo.parent.mkdir(parents=True, exist_ok=True)
        run([git, 'clone', '--filter=blob:none', UA_REPOSITORY, repo])
    if not core_ready(node, plugin):
        pnpm = need_command('pnpm', 10)
        run([pnpm, 'install', '--frozen-lockfile'], cwd=repo)
        run([pnpm, '--filter', '@understand-anything/core', 'build'], cwd=repo)
        if not core_ready(node, plugin):
            raise ValueError('UA core is still unavailable after building; graph-ma was not installed.')
    print(f'UA ready: {plugin}')
    return plugin.resolve()


def is_link(path):
    if path.is_symlink():
        return True
    try:
        attributes = path.lstat().st_file_attributes
        return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False


def exists(path):
    return path.exists() or is_link(path)


def same_directory(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def resource_files(source):
    for name in RESOURCES:
        path = source / name
        if not path.exists():
            raise ValueError(f'Incomplete graph-ma source: missing {path}')
        for item in sorted(path.rglob('*')) if path.is_dir() else [path]:
            if item.is_file() and '__pycache__' not in item.parts and item.suffix not in ('.pyc', '.pyo'):
                yield item.relative_to(source)


def same_skill(source, destination):
    return destination.is_dir() and all((destination / rel).is_file()
        and (source / rel).read_bytes() == (destination / rel).read_bytes()
        for rel in resource_files(source))


def preflight(source, skills, plugin, replace, plugin_link=None):
    for name in ('scripts', 'references', 'agents'):
        if skills.is_relative_to((source / name).resolve()):
            raise ValueError('The skills directory cannot be inside graph-ma resource directories.')
    target = skills / 'graph-ma'
    if exists(target) and not same_directory(source, target) and not same_skill(source, target) and not replace:
        raise ValueError(f'{target} has different files. Use --replace to back it up before replacing it.')
    if plugin:
        locator = target / 'ua-runtime.json'
        if locator.is_file() and (same_directory(source, target) or same_skill(source, target)):
            if json.loads(locator.read_text(encoding='utf-8')).get('installed_by') != 'graph-ma':
                raise ValueError(f'Preserving unmanaged locator: {locator}')
        if plugin_link and exists(plugin_link) and not same_directory(plugin, plugin_link) and not replace:
            raise ValueError(f'{plugin_link} already exists. Use --replace to preserve it as a backup.')
        for skill in sorted((plugin / 'skills').iterdir()):
            if not (skill / 'SKILL.md').is_file():
                continue
            if skill.name == 'graph-ma':
                raise ValueError('UA unexpectedly contains a graph-ma skill; refusing a name collision.')
            destination = skills / skill.name
            if exists(destination) and not same_directory(skill, destination) and not replace:
                raise ValueError(f'{destination} already exists. Use --replace to back it up before linking UA.')


def backup_destination(path, skills):
    # Rename only entries inside the explicitly selected skills directory.
    # Junctions/symlinks are renamed as entries; never walk or delete their targets.
    if path.parent.resolve() != skills.resolve():
        raise ValueError(f'Backup path escapes selected skills directory: {path}')
    backup_root = (skills / '.graph-ma-backups').resolve()
    if not backup_root.is_relative_to(skills.resolve()):
        raise ValueError(f'Backup directory escapes selected destination: {backup_root}')
    backup_root.mkdir(exist_ok=True)
    backup = backup_root / (path.name + '-' + uuid.uuid4().hex[:12])
    if not is_link(path) and path.resolve().parent != skills.resolve():
        raise ValueError(f'Unexpected resolved backup source: {path}')
    path.rename(backup)
    print(f'Backup: {backup}')
    return backup


def link_directory(source, destination):
    if os.name == 'nt':
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        environment = dict(os.environ, GRAPH_MA_LINK=str(destination), GRAPH_MA_LINK_TARGET=str(source))
        run([powershell, '-NoProfile', '-NonInteractive', '-Command',
             "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:GRAPH_MA_LINK -Target $env:GRAPH_MA_LINK_TARGET | Out-Null"],
            env=environment)
    else:
        destination.symlink_to(source, target_is_directory=True)


def install_link(source, destination, skills):
    if same_directory(source, destination):
        return
    backup = backup_destination(destination, skills) if exists(destination) else None
    try:
        link_directory(source, destination)
    except Exception:
        if backup and not exists(destination):
            backup.rename(destination)
        raise


def install_graphma(source, skills):
    destination = skills / 'graph-ma'
    if same_directory(source, destination) or same_skill(source, destination):
        print(f'graph-ma files already current: {destination}')
        return destination
    staging = skills / ('.graph-ma-install-' + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for rel in resource_files(source):
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, target)
        backup = backup_destination(destination, skills) if exists(destination) else None
        try:
            staging.rename(destination)
        except Exception:
            if backup and not exists(destination):
                backup.rename(destination)
            raise
    except Exception:
        print(f'Incomplete staged files were preserved at {staging}', file=sys.stderr)
        raise
    return destination


def install(source, skills, ua_repo, skip_ua=False, replace=False, plugin_link=None):
    source, skills, ua_repo = source.resolve(strict=True), skills.expanduser().resolve(), ua_repo.expanduser().resolve()
    # Check graph-ma conflicts before downloading dependencies.
    preflight(source, skills, None, replace)
    plugin = None if skip_ua else ensure_ua(ua_repo)
    plugin_link = plugin_link or Path.home() / '.understand-anything-plugin'
    # Keep a link's lexical path: resolve() would select and replace its target.
    plugin_link = plugin_link.expanduser().absolute()
    preflight(source, skills, plugin, replace, plugin_link)
    skills.mkdir(parents=True, exist_ok=True)
    if plugin:
        plugin_link.parent.mkdir(parents=True, exist_ok=True)
        install_link(plugin, plugin_link, plugin_link.parent)
        for skill in sorted((plugin / 'skills').iterdir()):
            if (skill / 'SKILL.md').is_file():
                install_link(skill, skills / skill.name, skills)
    destination = install_graphma(source, skills)
    if plugin:
        # Machine-local locator, not part of the portable source-analysis graph.
        locator = destination / 'ua-runtime.json'
        metadata = {'plugin_root': str(plugin), 'installed_by': 'graph-ma'}
        encoded = json.dumps(metadata, ensure_ascii=False, indent=2) + '\n'
        if not locator.exists() or locator.read_text(encoding='utf-8') != encoded:
            if locator.exists() and json.loads(locator.read_text(encoding='utf-8')).get('installed_by') != 'graph-ma':
                raise ValueError(f'Preserving unmanaged locator: {locator}')
            locator.write_text(encoded, encoding='utf-8')
    print(f'Installed graph-ma: {destination}')
    print('UA was skipped.' if skip_ua else 'UA skills linked; runtime verified. Dashboard is available but was not started.')
    print('Restart your host, then use $graph-ma.')
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    parser.add_argument('--skills-dir', type=Path, default=codex_home / 'skills')
    parser.add_argument('--ua-dir', type=Path, default=Path.home() / '.understand-anything/repo')
    parser.add_argument('--skip-ua', action='store_true', help='Install only graph-ma, without UA or Node/pnpm requirements')
    parser.add_argument('--replace', action='store_true', help='Back up conflicting skills before replacing them')
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise ValueError('Python 3.10+ is required.')
        install(SKILL_ROOT, args.skills_dir, args.ua_dir, args.skip_ua, args.replace)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'Installation failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
