"""生成 gen_* scenario_id。"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _slug(text: str) -> str:
    raw = unicodedata.normalize("NFKD", text or "")
    ascii_part = raw.encode("ascii", "ignore").decode("ascii").lower()
    ascii_part = _SLUG_RE.sub("_", ascii_part).strip("_")
    if ascii_part and not ascii_part.isdigit() and len(ascii_part) >= 3:
        return ascii_part[:24]
    digest = hashlib.sha256((text or "seed").encode("utf-8")).hexdigest()
    return f"pack_{digest[:8]}"


def make_scenario_id(title: str, seed: str) -> str:
    slug = _slug(title) or "pack"
    hex6 = hashlib.sha256(f"{title}|{seed}".encode("utf-8")).hexdigest()[:6]
    return f"gen_{slug}_{hex6}"


def is_generated_id(scenario_id: str) -> bool:
    return bool(scenario_id) and str(scenario_id).startswith("gen_")
