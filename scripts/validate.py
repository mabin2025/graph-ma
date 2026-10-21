#!/usr/bin/env python3
"""Check Markdown assets, SVG references and recorded source locations (stdlib only)."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from analysis import check_shape, emit, inventory, read_json, within


def svg_issues(path, require_description=False):
    root = ET.parse(path).getroot()
    issues = []
    if root.tag.split('}')[-1] != 'svg':
        issues.append('root element is not svg')
    ids = [e.attrib['id'] for e in root.iter() if 'id' in e.attrib]
    if len(ids) != len(set(ids)):
        issues.append('duplicate SVG ids')
    if require_description and not any(e.tag.split('}')[-1] == 'title' and ''.join(e.itertext()).strip() for e in root):
        issues.append('missing nonempty title')
    if require_description and not any(e.tag.split('}')[-1] == 'desc' and ''.join(e.itertext()).strip() for e in root):
        issues.append('missing nonempty desc')
    refs = set()
    for e in root.iter():
        for key, value in e.attrib.items():
            refs.update(re.findall(r'url\(\s*[\'"]?#([^\s)\'"]+)', value))
            if key.split('}')[-1] == 'href' and value.startswith('#'):
                refs.add(value[1:])
        if e.tag.split('}')[-1] == 'style' and e.text:
            refs.update(re.findall(r'url\(\s*[\'"]?#([^\s)\'"]+)', e.text))
    issues.extend(f'missing SVG reference #{ref}' for ref in sorted(refs - set(ids)))
    return issues


def image_links(text):
    # Ignore fenced/inline code: documentation examples are not asset references.
    text = re.sub(r'^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', text, flags=re.M | re.S)
    text = re.sub(r'`[^`\n]+`', '', text)
    links = re.findall(r'!\[[^\]\n]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[\'"][^\n]*?[\'"])?\s*\)', text)
    result = [a or b for a, b in links]
    definitions = {m[0].strip().casefold(): m[1] or m[2] for m in re.findall(r'^\s*\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))', text, flags=re.M)}
    missing = []
    for label, ref in re.findall(r'!\[([^\]]*)\]\[([^\]]*)\]', text):
        key = (ref or label).strip().casefold()
        if key in definitions:
            result.append(definitions[key])
        else:
            missing.append(f'undefined image reference [{ref or label}]')
    for value in re.findall(r'!\[\[([^\]]+)\]\]', text):
        result.append(value.split('|', 1)[0])
    return result, missing


def validate(document=None, analysis_path=None, project=None, flowcharts=()):
    errors, warnings = [], []
    required_descriptions = {Path(p).resolve() for p in flowcharts}
    svg_paths = set(required_descriptions)
    document = Path(document).resolve() if document else None
    if document:
        links, missing = image_links(document.read_text(encoding='utf-8-sig'))
        errors.extend(missing)
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc or link.startswith('#'):
                warnings.append(f'External/absolute image not checked: {link}')
                continue
            name = unquote(parsed.path)
            target = (document.parent / name).resolve()
            if not target.is_file():
                errors.append(f'Missing image: {link}')
            elif target.suffix.lower() == '.svg':
                svg_paths.add(target)
    if analysis_path:
        root = Path(project).resolve(strict=True)
        data = check_shape(read_json(analysis_path))
        current = inventory(root, data['scope'])
        for m in data.get('modules', []):
            for source in m.get('sources', []):
                if source not in current:
                    errors.append(f'{m["id"]}: missing or out-of-scope source {source}')
            for asset in m.get('assets', []):
                target = within(Path(analysis_path).resolve().parent, asset)
                if not target.is_file():
                    errors.append(f'{m["id"]}: missing asset {asset}')
                elif target.suffix.lower() == '.svg':
                    svg_paths.add(target)
        for c in data.get('claims', []):
            for e in c.get('evidence', []):
                target = within(root, e['path'])
                if not target.is_file():
                    errors.append(f'{c["id"]}: missing evidence {e["path"]}')
                    continue
                if e['path'] not in current:
                    errors.append(f'{c["id"]}: evidence outside scope {e["path"]}')
                content = target.read_text(encoding='utf-8-sig') if 'cell' in e or 'lines' in e else ''
                if 'cell' in e:
                    cells = json.loads(content)['cells']
                    if e['cell'] > len(cells):
                        errors.append(f'{c["id"]}: cell {e["cell"]} out of range')
                        continue
                    cell = cells[e['cell'] - 1]
                    if e.get('cell_id') is not None and cell.get('id') != e['cell_id']:
                        errors.append(f'{c["id"]}: cell_id moved or changed; relocate the evidence')
                    content = ''.join(cell.get('source', []))
                elif 'cell_id' in e:
                    errors.append(f'{c["id"]}: cell_id requires a 1-based cell position')
                if 'lines' in e and e['lines'][1] > len(content.splitlines()):
                    errors.append(f'{c["id"]}: line range exceeds evidence source')
        revision = data.get('revision')
        if not revision:
            warnings.append('No baseline yet; record snapshot only after reviewing source, prose and rendered images')
        elif revision.get('files') != current:
            warnings.append('Source differs from baseline; run analysis.py changes before using old conclusions')
    for path in sorted(svg_paths):
        try:
            errors.extend(f'{path.name}: {issue}' for issue in svg_issues(path, path in required_descriptions))
        except (OSError, ET.ParseError) as exc:
            errors.append(f'{path.name}: {exc}')
    return {'errors': errors, 'warnings': warnings, 'svg_checked': len(svg_paths),
            'limits': 'Checks location/structure only. Verify claim meaning against source and render images for visual review.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document', type=Path)
    parser.add_argument('--analysis', type=Path)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--flowchart', type=Path, action='append', default=[], help='SVG diagram requiring title/desc; repeatable')
    args = parser.parse_args()
    if not (args.document or args.analysis or args.flowchart) or (args.analysis and not args.project):
        parser.error('provide --document, --flowchart, or --analysis with --project')
    try:
        result = validate(args.document, args.analysis, args.project, args.flowchart)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {'errors': [str(exc)], 'warnings': []}
    emit(result)
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
