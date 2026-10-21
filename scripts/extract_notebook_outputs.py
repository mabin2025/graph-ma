#!/usr/bin/env python3
"""Extract selected saved Notebook images and their provenance without executing cells."""
import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from analysis import emit

MIMES = {'image/svg+xml': '.svg', 'image/png': '.png', 'image/jpeg': '.jpg'}


def extract(notebook, output, cells, mime=None):
    notebook, output = Path(notebook), Path(output)
    raw = notebook.read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    selected = sorted(set(cells))
    if not selected or any(n < 1 or n > len(data['cells']) for n in selected):
        raise ValueError('Select existing cells by 1-based file position')
    planned, sources = [], []
    stem = re.sub(r'[^\w.-]', '_', notebook.stem)
    for n in selected:
        cell = data['cells'][n - 1]
        source = ''.join(cell.get('source', []))
        for index, entry in enumerate(cell.get('outputs', []), 1):
            saved = entry.get('data', {})
            chosen = next((m for m in ([mime] if mime else MIMES) if m in saved), None)
            if chosen is None:
                continue
            value = ''.join(saved[chosen]) if isinstance(saved[chosen], list) else saved[chosen]
            if chosen == 'image/svg+xml':
                image = value.encode('utf-8')
                if ET.fromstring(image).tag.split('}')[-1] != 'svg':
                    raise ValueError(f'Cell {n}, output {index}: invalid SVG root')
            else:
                image = base64.b64decode(''.join(value.split()), validate=True)
                if chosen == 'image/png' and not image.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError(f'Cell {n}, output {index}: invalid PNG signature')
                if chosen == 'image/jpeg' and not image.startswith(b'\xff\xd8\xff'):
                    raise ValueError(f'Cell {n}, output {index}: invalid JPEG signature')
            name = f'{stem}-cell-{n}-output-{index}{MIMES[chosen]}'
            planned.append((output / name, image))
            sources.append({'asset': name, 'notebook': notebook.name, 'notebook_sha256': hashlib.sha256(raw).hexdigest(),
                            'cell': n, 'cell_id': cell.get('id'), 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                            'output': index, 'mime': chosen, 'asset_sha256': hashlib.sha256(image).hexdigest(),
                            'kind': 'historical', 'note': 'Saved output; extraction does not establish when or from which code it was produced.'})
    if not sources:
        raise ValueError('Selected cells contain no supported saved image outputs')
    metadata = output / f'{stem}-sources.json'
    # Preflight every destination so a second invocation cannot replace user assets.
    for path, _ in planned + [(metadata, b'')]:
        if path.exists():
            raise ValueError(f'Refusing to overwrite: {path}')
    output.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for path, content in planned:
            with path.open('xb') as f:
                created.append(path)
                f.write(content)
        with metadata.open('x', encoding='utf-8', newline='\n') as f:
            created.append(metadata)
            json.dump(sources, f, ensure_ascii=False, indent=2)
            f.write('\n')
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('notebook', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cells', required=True, help='1-based positions, comma-separated; execution counts are ignored')
    parser.add_argument('--mime', choices=list(MIMES))
    args = parser.parse_args()
    try:
        result = extract(args.notebook, args.output, [int(x) for x in args.cells.split(',')], args.mime)
        emit({'images': result})
        return 0
    except (OSError, ValueError, TypeError, KeyError, binascii.Error, ET.ParseError) as exc:
        emit({'error': str(exc)})
        return 1


if __name__ == '__main__':
    sys.exit(main())
