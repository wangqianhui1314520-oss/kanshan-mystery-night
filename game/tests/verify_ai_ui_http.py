"""Refresh changed asset versions and verify the local integration server."""
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen

front = Path(__file__).resolve().parents[1] / 'frontend'
index = front / 'index.html'
html = index.read_text(encoding='utf-8')
for name in ('js/main.js', 'js/ux.js', 'css/ux.css'):
    digest = hashlib.sha256((front / name).read_bytes()).hexdigest()[:12]
    html = re.sub(re.escape(name) + r'\?v=[^"\s]+', name + '?v=' + digest, html)
index.write_text(html, encoding='utf-8')
base = 'http://127.0.0.1:8901'
with urlopen(base + '/api/health', timeout=5) as response:
    data = json.load(response)
assert data['ai']['build'] == 'ai-status-ui-20260914'
with urlopen(base + '/', timeout=5) as response:
    served = response.read().decode('utf-8')
assert served.replace('\r\n', '\n') == html
for name in ('js/main.js', 'js/ux.js', 'css/ux.css'):
    with urlopen(base + '/' + name, timeout=5) as response:
        assert response.read() == (front / name).read_bytes()
print('PASS: health schema, served HTML, three current assets; AI state:', data['ai']['state'])
