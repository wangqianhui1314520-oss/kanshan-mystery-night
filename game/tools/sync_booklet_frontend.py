"""Rebuild the offline booklet mirror and fingerprint changed entry assets."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sync():
    target = ROOT / 'frontend/js/booklets.js'
    source = target.read_text(encoding='utf-8')
    start = source.index('window.BOOKLET_DATA = ') + len('window.BOOKLET_DATA = ')
    _, length = json.JSONDecoder().raw_decode(source[start:])
    data = {}
    for path in sorted((ROOT / 'content/scenarios/kanshan/booklets').glob('*.json')):
        row = json.loads(path.read_text(encoding='utf-8'))
        if row.get('id'):
            row.pop('faction', None)
            data[row['id']] = row
    target.write_text(source[:start] + json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                      + source[start + length:], encoding='utf-8')
    index = ROOT / 'frontend/index.html'
    html = index.read_text(encoding='utf-8')
    for rel in ('js/booklets.js', 'js/store.js', 'js/main.js', 'css/v31.css'):
        digest = hashlib.sha256((ROOT / 'frontend' / rel).read_bytes()).hexdigest()[:12]
        html = re.sub(re.escape(rel) + r'\?v=[^"\s]+', rel + '?v=' + digest, html)
    index.write_text(html, encoding='utf-8')
    print(f'Synchronized {len(data)} booklets and asset versions.')


if __name__ == '__main__':
    sync()
