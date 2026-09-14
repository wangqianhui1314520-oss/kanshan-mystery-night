#!/usr/bin/env python3
"""静态资产引用自检（只读，零副作用）

扫描 frontend/ 下所有 js/css/html（排除第三方 vendor），提取三类引用：
  1. 字面量路径  /assets/xxx.png
  2. 变量拼接    IMG + 'xxx.png'   /   VID + 'xxx.mp4'
  3. 音频引用    new Audio(...) / playSound / <audio src=...>
与磁盘实际文件、服务端 HTTP 响应三方比对，输出缺口清单。
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
ASSETS = GAME / "content" / "assets"
BASE = "http://127.0.0.1:8899"

# 引用侧不止前端：服务端下发的 возьми payload 也带资产 URL（如 engine_driver 的幕转场图），
# 只扫 frontend 会误报孤儿，故一并扫描 server/ 与 engine/。
SCAN_DIRS = [GAME / "frontend", GAME / "server", GAME / "engine"]

# 字面量路径；允许内含 {...} 以覆盖 f-string 模板（如 act_t{min(act,3)}.png）
RE_LITERAL = re.compile(
    r"/assets/([A-Za-z0-9_\-./{}()\w,\s]+\.(?:png|jpe?g|gif|svg|webp|mp4|webm|mp3|wav|ogg|aac|m4a))"
)
# 变量拼接：必须连同前缀变量一起捕获，否则丢掉子目录（IMG→images/、VID→videos/）
RE_CONCAT = re.compile(r"\b(IMG|VID|AUD|SND|BUST|STILL|CARD)\s*\+\s*'([^']+)'")
PREFIX_DIR = {"IMG": "images/", "VID": "videos/", "AUD": "audio/", "SND": "audio/", "BUST": "images/bust/", "STILL": "images/still/", "CARD": "images/card/"}
RE_AUDIO = re.compile(r"(?:new\s+Audio\(|Audio\(|playSound\(|sfx\s*\()\s*['\"]([^'\"]+)['\"]")

SCAN_EXT = {".js", ".css", ".html", ".py", ".pyi"}   # 服务端 .py 也带资产 URL，勿漏
SKIP_PARTS = {"vendor"}


def iter_source_files():
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_dir() or not p.is_file():
                continue
            if p.suffix not in SCAN_EXT:
                continue
            if SKIP_PARTS & set(p.parts):
                continue
            if p.name.startswith("_e2e") or p.name.startswith("_ chk"):
                continue
            yield p


def resolve_disk(rel: str) -> tuple[bool, int, list[str]]:
    """返回 (是否存在, 总字节, 实际匹配到的相对路径列表)。支持 f-string 通配。"""
    if "{" in rel:                       # 动态模板：act_t{min(...)}.png → glob 匹配
        pat = re.sub(r"\{[^}]*\}", "*", rel)
        hits = sorted({q.relative_to(ASSETS).as_posix() for q in ASSETS.glob(pat)})
        if hits:
            sz = sum((ASSETS / h).stat().st_size for h in hits)
            return True, sz, hits
        return False, 0, []
    disk = ASSETS / rel
    return (disk.exists(), disk.stat().st_size if disk.exists() else 0, [rel])


def collect() -> dict[str, set[tuple[str, str]]]:
    """rel -> {(file:line, kind)} 收集所有引用"""
    found: dict[str, set[tuple[str, str]]] = {}
    for p in iter_source_files():
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        rel_file = p.relative_to(GAME).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            for m in RE_LITERAL.finditer(line):
                found.setdefault(m.group(1), set()).add((f"{rel_file}:{i}", "literal"))
            for m in RE_CONCAT.finditer(line):
                var, tail = m.group(1), m.group(2)
                rel = PREFIX_DIR.get(var, "") + tail
                found.setdefault(rel, set()).add((f"{rel_file}:{i}", f"concat:{var}"))
            for m in RE_AUDIO.finditer(line):
                raw = m.group(1)
                rel = raw if raw.startswith(("audio/", "/")) else "audio/" + raw
                rel = rel.lstrip("/")
                found.setdefault(rel, set()).add((f"{rel_file}:{i}", "audio"))
    return found


def http_status(rel: str) -> int:
    try:
        req = urllib.request.Request(f"{BASE}/assets/{rel}", method="HEAD")
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1


def main() -> int:
    found = collect()
    rows = []
    consumed: set[str] = set()
    for rel, sites in sorted(found.items()):
        exists, size, hits = resolve_disk(rel)
        consumed.update(hits)
        code = http_status(hits[0]) if hits else -2
        rows.append({
            "asset": rel, "kind": Path(rel).suffix.lower().lstrip("."),
            "ref_count": len(sites), "on_disk": exists, "bytes": size,
            "http": code, "resolves_to": hits, "sites": sorted(sites)[:4],
        })

    miss_disk = [r for r in rows if not r["on_disk"]]
    miss_http = [r for r in rows if r["on_disk"] and r["http"] != 200]
    zero = [r for r in rows if r["on_disk"] and r["bytes"] == 0]

    print("=" * 78)
    print(f"扫描文件数 : {len(list(iter_source_files()))}")
    print(f"被引用的资产 : {len(rows)}")
    print(f"  ✅ 磁盘存在且 HTTP 200 : {len(rows) - len(miss_disk) - len(miss_http)}")
    print(f"  ❌ 磁盘缺失             : {len(miss_disk)}")
    print(f"  ⚠️  磁盘有但 HTTP 非200 : {len(miss_http)}")
    print(f"  ⚠️  磁盘存在但 0 字节   : {len(zero)}")
    print("=" * 78)

    if miss_disk:
        print("\n【缺失资产明细】")
        for r in miss_disk:
            print(f"  - {r['asset']}  ({r['kind']}, 被引用 {r['ref_count']} 处)")
            for s, _ in r["sites"]:
                print(f"      {s}")

    if miss_http:
        print("\n【HTTP 异常明细】")
        for r in miss_http:
            print(f"  - {r['asset']}  HTTP {r['http']}  ({r['bytes']} bytes)")

    if zero:
        print("\n【0 字节文件】")
        for r in zero:
            print(f"  - {r['asset']}")

    # 反向检查：磁盘上有但从未被引用（已计入动态模板命中）
    orphans = []
    for p in ASSETS.rglob("*"):
        if p.is_file() and p.name not in ("README.md", ".gitignore"):
            rel = p.relative_to(ASSETS).as_posix()
            if rel not in consumed:
                orphans.append((rel, p.stat().st_size))
    print(f"\n【孤儿资产】磁盘存在但前端从未引用: {len(orphans)}")
    for rel, sz in sorted(orphans)[:40]:
        print(f"  - {rel}  ({sz // 1024} KB)")

    # 按类型汇总
    print("\n【按类型汇总】")
    from collections import Counter
    for k, c in sorted(Counter(Path(r['asset']).suffix.lower().lstrip('.') for r in rows).items()):
        sub = [r for r in rows if Path(r['asset']).suffix.lower().lstrip('.') == k]
        ok = sum(1 for r in sub if r["on_disk"] and r["http"] == 200)
        print(f"  {k:6s} 引用 {c:3d}  可用 {ok:3d}  缺失 {c - ok:3d}")

    (GAME / "data").mkdir(exist_ok=True)
    out = GAME / "data" / "_asset_check.json"
    out.write_text(json.dumps({"rows": rows, "orphans": orphans}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完整结果: {out.relative_to(GAME).as_posix()}")

    return 1 if (miss_disk or miss_http or zero) else 0


if __name__ == "__main__":
    sys.exit(main())
