"""Refresh local JS/CSS URLs after edits so a page reload fetches the new files."""
import hashlib
import re
from pathlib import Path


def update(frontend: Path) -> int:
    index = frontend / "index.html"
    source = index.read_text(encoding="utf-8")
    changed = 0

    def version(match: re.Match) -> str:
        nonlocal changed
        path = frontend / match[2]
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        replacement = f'{match[1]}="{match[2]}?v={digest}"'
        changed += replacement != match[0]
        return replacement

    updated = re.sub(
        r'(src|href)="((?:js|css|minis)/[^"?]+\.(?:js|css))(?:\?v=[^"?]+)?"',
        version, source,
    )
    if changed:
        index.write_text(updated, encoding="utf-8", newline="\n")
    return changed


if __name__ == "__main__":
    count = update(Path(__file__).resolve().parents[1] / "frontend")
    print(f"Updated {count} frontend resource URLs.")
