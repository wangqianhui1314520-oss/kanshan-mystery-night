"""QA 探针：验证 ConsistencyGuard 对正常 NPC 回复的误杀率（只读，零网络）。

用真实剧本数据（char_03/char_01 secret + booklet must_not hints + truth）+
贴近游玩的真实回复样本，输出每条回复的 violations 明细。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME_ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from agents.consistency_guard import ConsistencyGuard, _grams  # noqa: E402

SCN = GAME_ROOT / "content" / "scenarios" / "kanshan"


def main():
    truth = json.loads((SCN / "truth.json").read_text(encoding="utf-8"))
    timeline = None  # 时间线校验需引擎对象，此处聚焦泄密/禁语误杀
    guard = ConsistencyGuard(timeline, None, truth)

    # 样本回复：都是"正常游玩中 AI 应该能说出口"的话（不含任何秘密设定）
    samples = [
        "我那晚 11 点还在工位加班，走的时候茶水间的灯都没关。",
        "帖子确实是我发的，但内容不是我写的，有人把钱打到账上让我照发。",
        "看山失踪前一周就在内部群说过有人偷改他的档案，我亲耳听到。",
        "监控那天坏了一半，机房钥匙只有局长有。",
        "我当时在前台拿快递，没注意到谁进了档案室。",
        "热搜爆的时候我正在茶水间泡面，同事都在刷手机。",
        "我知道的都说了，再问就要问档案局大门的锁是谁配的钥匙了。",
    ]
    char_ids = ["char_01", "char_03"]
    chars = {cid: json.loads((SCN / "characters" / f"{cid}.json").read_text(
        encoding="utf-8")) for cid in char_ids}
    # booklet must_not hints（模拟 npc_social 实际传入的禁语）
    must_not = {}
    try:
        sys.path.insert(0, str(GAME_ROOT))
        from engine.booklet import load_library, stage_to_chapter
        lib = load_library(SCN)
        for cid in char_ids:
            hints = lib.merged_hints(cid, stage_to_chapter("break_ice"))
            must_not[cid] = list(hints.get("must_not") or [])
    except Exception as e:
        print("booklet hints 加载失败（不影响泄密检测探针）：", e)

    total, killed = 0, 0
    for cid in char_ids:
        ch = chars[cid]
        print(f"\n===== {cid} {ch.get('name')} =====")
        print(f"must_not_say = {must_not.get(cid)}")
        for s in samples:
            total += 1
            v = guard.check(ch, s, {"trust": 0, "stage": "break_ice",
                                    "memory_state": {"heart_unlocked": False, "blocks": []},
                                    "must_not_say": must_not.get(cid, [])})
            tag = "KILLED" if v else "pass  "
            if v:
                killed += 1
            print(f"[{tag}] {s[:34]:<36} -> {v}")

    # 额外：把 char_03 的 secret(guilt/motive) 打出来对齐 2-gram 重叠阈值
    print("\n===== secret 文本（只看长度与开头，评估误杀面） =====")
    for cid in char_ids:
        sec = (chars[cid].get("secret") or {})
        for k in ("guilt", "motive"):
            t = str(sec.get(k) or "")
            if t:
                print(f"{cid}.{k}: len={len(t)} head={t[:20]}…")

    print(f"\n===== SUMMARY: {killed}/{total} 正常回复被拦截"
          f"（{killed/total*100:.0f}% 误杀率样本） =====")


if __name__ == "__main__":
    main()
