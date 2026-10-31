#!/usr/bin/env python3
"""Read-only UA graph checks, bounded keyword navigation and source-drift reporting."""
import argparse
import math
from pathlib import Path
import subprocess

from analysis import changes, check_shape, emit, read_json, within
from validate import validate

NODE_TYPES = set(('file function class module concept config document service table endpoint '
                  'pipeline schema resource domain flow step article entity topic claim source '
                  'page screen component componentSet instance token').split())
EDGE_TYPES = set(('imports exports contains inherits implements calls subscribes publishes middleware '
                  'reads_from writes_to transforms validates depends_on tested_by configures related '
                  'similar_to deploys serves provisions triggers migrates documents routes defines_schema '
                  'contains_flow flow_step cross_domain cites contradicts builds_on exemplifies '
                  'categorized_under authored_by instance_of variant_of uses_token').split())
FILE_TYPES = {'file', 'config', 'document', 'service', 'pipeline', 'schema', 'resource'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strings(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def check_graph(data, root=None, check_sources=True):
    """Check the codebase interchange fields; this is not the full upstream schema."""
    require(isinstance(data, dict) and isinstance(data.get('version'), str), 'Missing graph version')
    project = data.get('project')
    require(isinstance(project, dict), 'Missing project metadata')
    for key in ('name', 'description', 'analyzedAt', 'gitCommitHash'):
        require(isinstance(project.get(key), str), f'project.{key} must be a string')
    for key in ('languages', 'frameworks'):
        require(strings(project.get(key)), f'project.{key} must be an array of strings')
    for key in ('nodes', 'edges', 'layers', 'tour'):
        require(isinstance(data.get(key), list), f'{key} must be an array')
    ids = set()
    for node in data['nodes']:
        require(isinstance(node, dict), 'Node must be an object')
        node_id = node.get('id')
        require(isinstance(node_id, str) and node_id and node_id not in ids, f'Invalid/duplicate node id: {node_id}')
        ids.add(node_id)
        require(isinstance(node.get('type'), str) and node['type'] in NODE_TYPES, f'{node_id}: unknown node type')
        for key in ('name', 'summary'):
            require(isinstance(node.get(key), str) and node[key].strip(), f'{node_id}: missing {key}')
        require(strings(node.get('tags')), f'{node_id}: tags must be strings')
        require(node.get('complexity') in ('simple', 'moderate', 'complex'), f'{node_id}: invalid complexity')
        path = node.get('filePath')
        require(path is not None or node['type'] not in FILE_TYPES, f'{node_id}: missing filePath')
        target = None
        if path is not None:
            require(isinstance(path, str) and path and '\\' not in path, f'{node_id}: filePath must be a relative POSIX path')
            target = within(root or Path.cwd(), path)
            if root and check_sources:
                require(target.is_file(), f'{node_id}: missing source {path}')
        lines = node.get('lineRange')
        if lines is not None:
            require(isinstance(lines, list) and len(lines) == 2 and all(type(n) is int for n in lines)
                    and 1 <= lines[0] <= lines[1] and target is not None, f'{node_id}: invalid lineRange')
            if root and check_sources:
                require(lines[1] <= len(target.read_text(encoding='utf-8-sig').splitlines()),
                        f'{node_id}: lineRange exceeds source')
    for edge in data['edges']:
        require(isinstance(edge, dict), 'Edge must be an object')
        require(edge.get('source') in ids and edge.get('target') in ids, 'Dangling edge endpoint')
        require(isinstance(edge.get('type'), str) and edge['type'] in EDGE_TYPES, 'Unknown edge type')
        require(edge.get('direction') in ('forward', 'backward', 'bidirectional'), 'Invalid edge direction')
        weight = edge.get('weight')
        require(type(weight) in (int, float) and math.isfinite(weight) and 0 <= weight <= 1, 'Invalid edge weight')
    for key, identity in (('layers', 'id'), ('tour', 'order')):
        seen = set()
        for entry in data[key]:
            require(isinstance(entry, dict), f'{key} entry must be an object')
            value = entry.get(identity)
            valid = isinstance(value, str) and bool(value) if key == 'layers' else type(value) is int and value > 0
            require(valid and value not in seen, f'{key}: invalid/duplicate {identity}')
            seen.add(value)
            require(strings(entry.get('nodeIds')), f'{key}: nodeIds must be strings')
            require(set(entry['nodeIds']) <= ids, f'{key}: dangling node reference')
            for field in ('name', 'description') if key == 'layers' else ('title', 'description'):
                require(isinstance(entry.get(field), str), f'{key}: missing {field}')
    return ids


def query_graph(data, terms, hops=1, limit=20):
    require(type(hops) is int and 0 <= hops <= 2, 'hops must be 0..2')
    require(type(limit) is int and 1 <= limit <= 200, 'limit must be 1..200')
    words = [t.casefold() for t in terms if t.strip()]
    require(words, 'Provide at least one query keyword')
    nodes = data['nodes']
    matches = []
    for node in nodes:
        haystack = ' '.join([node['id'], node['name'], node.get('filePath', ''), node['summary'], *node['tags']]).casefold()
        if any(word in haystack for word in words):
            matches.append(node['id'])
    selected = set(matches[:limit])
    for _ in range(hops):
        neighbors = set()
        for edge in data['edges']:
            if edge['source'] in selected:
                neighbors.add(edge['target'])
            if edge['target'] in selected:
                neighbors.add(edge['source'])
        # Stable graph order and a hard node cap even for a high-degree hub.
        for node in nodes:
            if len(selected) >= limit:
                break
            if node['id'] in neighbors:
                selected.add(node['id'])
    edges = [e for e in data['edges'] if e['source'] in selected and e['target'] in selected]
    result = {'project': data['project'], 'matched_count': len(matches),
              'nodes': [n for n in nodes if n['id'] in selected], 'edges': edges[:limit * 4],
              'omitted_edges': max(0, len(edges) - limit * 4)}
    for key in ('layers', 'tour'):
        related = [dict(item, nodeIds=[n for n in item['nodeIds'] if n in selected])
                   for item in data[key] if selected.intersection(item['nodeIds'])]
        result[key] = related[:limit]
        result[f'omitted_{key}'] = max(0, len(related) - limit)
    return result


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode('utf-8')


def freshness(data, root, graph_path):
    """Inspect project-scoped Git drift, including uncommitted and untracked files."""
    try:
        head = git(root, 'rev-parse', '--verify', 'HEAD').strip()
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        return {'state': 'unknown', 'reason': 'Git/HEAD unavailable; verify source or use an analysis baseline'}
    raw = data['project']['gitCommitHash']
    try:
        # Metadata stays a separate argv element; resolve to a commit before diffing.
        base = git(root, 'rev-parse', '--verify', '--end-of-options', raw + '^{commit}').strip() if raw else None
    except (OSError, subprocess.CalledProcessError):
        base = None
    try:
        commands = [
            ('staged', ('diff', '--relative', '--name-only', '-z', '--cached', '--', '.')),
            ('unstaged', ('diff', '--relative', '--name-only', '-z', '--', '.')),
            ('untracked', ('ls-files', '-z', '--others', '--exclude-standard', '--', '.')),
        ]
        if base:
            commands.insert(0, ('committed', ('diff', '--relative', '--name-only', '-z', base, head, '--', '.')))
        own = graph_path.resolve().relative_to(root).as_posix() if graph_path.resolve().is_relative_to(root) else None
        changed = {}
        for label, args in commands:
            names = git(root, *args).split('\0')
            changed[label] = sorted({p for p in names if p and p != own
                                     and not {'.ua', '.understand-anything'}.intersection(Path(p).parts)})
        state = 'changed' if any(changed.values()) else 'no_detected_changes' if base else 'unknown'
        return {'state': state, 'graph_commit': base, 'current_commit': head, 'files': changed,
                'limits': 'Git checks project paths, not graph semantics or ignored files; use analysis fingerprints too.'}
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        return {'state': 'unknown', 'reason': f'Git comparison failed: {exc}'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'query'])
    parser.add_argument('--graph', required=True, type=Path)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--analysis', type=Path)
    parser.add_argument('--query', nargs='+', default=[])
    parser.add_argument('--hops', type=int, default=1)
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    try:
        root = args.project.resolve(strict=True)
        require(root.is_dir(), 'project must be a directory')
        data = read_json(args.graph)
        ids = check_graph(data, root, check_sources=args.command == 'check')
        result = {'nodes_checked': len(ids), 'edges_checked': len(data['edges']), 'errors': [], 'warnings': [],
                  'freshness': freshness(data, root, args.graph),
                  'limits': 'Basic interchange/reference checks only; verify relationship meaning against current source.'}
        if args.analysis:
            analysis = check_shape(read_json(args.analysis))
            for module in analysis.get('modules', []):
                require(set(module.get('graph_node_ids', [])) <= ids, f'{module["id"]}: unknown graph_node_ids')
            validation = validate(analysis_path=args.analysis, project=root)
            result['errors'].extend(validation['errors'])
            result['warnings'].extend(validation['warnings'])
            result['analysis_changes'] = changes(analysis, root) if 'revision' in analysis else {'state': 'no_baseline'}
        if args.command == 'query':
            result['subgraph'] = query_graph(data, args.query, args.hops, args.limit)
        emit(result)
        return 1 if result['errors'] else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        emit({'errors': [str(exc)]})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
