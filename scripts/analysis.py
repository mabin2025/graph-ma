#!/usr/bin/env python3
"""Fingerprint a scoped analysis and report documentation affected by source drift."""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

KINDS = {'source', 'local', 'historical', 'run', 'inference', 'unverified'}
SKIP = {'.git', 'node_modules', '__pycache__', '.venv', '.ua', '.understand-anything'}


def emit(data):
    # Keep JSON interoperable on Windows consoles with legacy code pages.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(data, ensure_ascii=False, indent=2))


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def within(root, relative):
    """Source paths are relative, resolved, and may not escape the selected root."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f'Expected a relative path: {relative!r}')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes project: {relative}')
    return path


def check_shape(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('analysis.version must be 1')
    scope = data.get('scope', {})
    if not isinstance(scope, dict) or not isinstance(scope.get('paths'), list) or not scope['paths']:
        raise ValueError('scope.paths must be a nonempty array')
    if not all(isinstance(p, str) and p for p in scope['paths']):
        raise ValueError('scope.paths entries must be nonempty strings')
    if not isinstance(scope.get('exclude', []), list) or not all(isinstance(p, str) for p in scope.get('exclude', [])):
        raise ValueError('scope.exclude must be an array of glob strings')
    modules, claims = data.get('modules', []), data.get('claims', [])
    if not isinstance(modules, list) or not isinstance(claims, list):
        raise ValueError('modules and claims must be arrays')
    ids = set()
    for entry in modules + claims:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or not entry['id']:
            raise ValueError('Every module and claim needs a string id')
        if entry['id'] in ids:
            raise ValueError(f'Duplicate id: {entry["id"]}')
        ids.add(entry['id'])
    module_ids = {m['id'] for m in modules}
    for m in modules:
        for key in ('sources', 'depends_on', 'sections', 'assets'):
            if not isinstance(m.get(key, []), list) or not all(isinstance(x, str) and x for x in m.get(key, [])):
                raise ValueError(f'{m["id"]}.{key} must be an array of strings')
        if set(m.get('depends_on', [])) - module_ids:
            raise ValueError(f'Unknown dependency in {m["id"]}')
    for c in claims:
        if c.get('module') not in module_ids or c.get('kind') not in KINDS:
            raise ValueError(f'Invalid module or evidence kind in {c["id"]}')
        if not isinstance(c.get('text'), str) or not c['text'].strip():
            raise ValueError(f'Missing text in {c["id"]}')
        evidence = c.get('evidence', [])
        if not isinstance(evidence, list) or not all(isinstance(e, dict) and isinstance(e.get('path'), str) and e['path'] for e in evidence):
            raise ValueError(f'Invalid evidence in {c["id"]}')
        if c['kind'] not in {'inference', 'unverified'} and not evidence:
            raise ValueError(f'Grounded claim {c["id"]} needs evidence')
        for e in evidence:
            lines = e.get('lines')
            if lines is not None and (not isinstance(lines, list) or len(lines) != 2 or any(type(x) is not int for x in lines) or not 1 <= lines[0] <= lines[1]):
                raise ValueError(f'Invalid 1-based line range in {c["id"]}')
            if 'cell' in e and (type(e['cell']) is not int or e['cell'] < 1):
                raise ValueError(f'Invalid 1-based cell in {c["id"]}')
            if 'cell_id' in e and not isinstance(e['cell_id'], str):
                raise ValueError(f'Invalid cell_id in {c["id"]}')
    if 'revision' in data:
        revision = data['revision']
        if not isinstance(revision, dict) or not isinstance(revision.get('files'), dict):
            raise ValueError('revision.files must be a fingerprint object')
        for path, value in revision['files'].items():
            if not isinstance(path, str) or not isinstance(value, dict) or not isinstance(value.get('sha256'), str) or len(value['sha256']) != 64:
                raise ValueError('Invalid baseline file fingerprint')
    return data


def fingerprint(path):
    raw = path.read_bytes()
    result = {'sha256': hashlib.sha256(raw).hexdigest()}
    if path.suffix.lower() == '.ipynb':
        cells = json.loads(raw.decode('utf-8-sig')).get('cells', [])
        code = [''.join(c.get('source', [])) for c in cells if c.get('cell_type') == 'code']
        outputs = [c.get('outputs', []) for c in cells if c.get('cell_type') == 'code']
        for key, value in [('code_sha256', code), ('outputs_sha256', outputs)]:
            result[key] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return result


def inventory(root, scope):
    paths = set()
    for entry in scope['paths']:
        target = within(root, entry)
        candidates = []
        if target.is_dir():
            for folder, dirs, files in os.walk(target, followlinks=False):
                dirs[:] = [d for d in dirs if d not in SKIP and not (Path(folder) / d).is_symlink()]
                candidates.extend(Path(folder) / name for name in files)
        else:
            candidates = [target]
        for p in candidates:
            # Resolve symlinks before reading; directory symlinks are not followed.
            rel = p.relative_to(root).as_posix()
            if not p.is_file() or SKIP.intersection(Path(rel).parts):
                continue
            if any(fnmatch.fnmatchcase(rel, pat) for pat in scope.get('exclude', [])):
                continue
            within(root, rel)
            paths.add(p)
    return {p.relative_to(root).as_posix(): fingerprint(p) for p in sorted(paths)}


def git_head(root):
    try:
        return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def save_json(path, data, expected=None):
    """Replace atomically, refusing to overwrite a concurrently changed manifest."""
    path = Path(path)
    if expected is not None and path.read_bytes() != expected:
        raise ValueError('Analysis changed while computing; reload and merge first')
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False, newline='\n') as f:
            temp = Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        if expected is not None and path.read_bytes() != expected:
            raise ValueError('Analysis changed before save; reload and merge first')
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def changes(data, root):
    revision = data.get('revision', {})
    before = revision.get('files')
    if not isinstance(before, dict):
        raise ValueError('Missing baseline: verify the documents, then run snapshot')
    now = inventory(root, data['scope'])
    changed = sorted(p for p in set(before) | set(now) if before.get(p) != now.get(p))
    modules = data.get('modules', [])
    claims = data.get('claims', [])
    # Use source and evidence references, then propagate dependency impact to consumers.
    owners = {}
    for m in modules:
        for p in m.get('sources', []):
            owners.setdefault(p, set()).add(m['id'])
    for c in claims:
        for e in c.get('evidence', []):
            owners.setdefault(e['path'], set()).add(c['module'])
    unmapped = [p for p in changed if p not in owners]
    affected = set().union(*(owners.get(p, set()) for p in changed)) if changed else set()
    # New/unmapped scoped files may introduce routes/configuration the index does not know.
    if unmapped:
        affected.update(m['id'] for m in modules)
    while True:
        expanded = affected | {m['id'] for m in modules if affected.intersection(m.get('depends_on', []))}
        if expanded == affected:
            break
        affected = expanded
    details = []
    for p in changed:
        item = {'path': p, 'status': 'added' if p not in before else 'deleted' if p not in now else 'modified'}
        if p.endswith('.ipynb') and p in before and p in now:
            item['code_changed'] = before[p].get('code_sha256') != now[p].get('code_sha256')
            item['outputs_changed'] = before[p].get('outputs_sha256') != now[p].get('outputs_sha256')
        details.append(item)
    return {
        'changed_files': details,
        'unmapped_changes': unmapped,
        'affected_modules': sorted(affected),
        'affected_claims': [c['id'] for c in claims if c['module'] in affected],
        'sections': sorted({s for m in modules if m['id'] in affected for s in m.get('sections', [])}),
        'assets': sorted({a for m in modules if m['id'] in affected for a in m.get('assets', [])}),
        'baseline_commit': revision.get('git_commit'),
        'current_commit': git_head(root),
        'limits': 'Impact is limited to scope.paths and recorded dependencies; runtime behavior still needs source review.'
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'changes'])
    parser.add_argument('--analysis', required=True, type=Path)
    parser.add_argument('--project', required=True, type=Path)
    args = parser.parse_args()
    try:
        original = args.analysis.read_bytes()
        data = check_shape(json.loads(original.decode('utf-8-sig')))
        root = args.project.resolve(strict=True)
        if not root.is_dir():
            raise ValueError('project must be a directory')
        if args.command == 'changes':
            result = changes(data, root)
        else:
            # Do not hash the generated analysis itself: that creates permanent self drift.
            current = inventory(root, data['scope'])
            rel = args.analysis.resolve().relative_to(root).as_posix() if args.analysis.resolve().is_relative_to(root) else None
            if rel in current:
                raise ValueError('Exclude the generated analysis/document directory from scope.paths')
            if not current:
                raise ValueError('Scope contains no files; check paths before recording a baseline')
            data['revision'] = {'git_commit': git_head(root), 'files': current}
            save_json(args.analysis, data, expected=original)
            result = {'snapshot_files': len(current), 'analysis': str(args.analysis)}
        emit(result)
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        emit({'error': str(exc)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
