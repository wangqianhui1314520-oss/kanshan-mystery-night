"""memory_system — 双层记忆引擎（said/heart）

契约：docs/CONTRACTS.md §3.2；设计：docs/STORY_ADAPTATION.md 第二幕「心声泄露」。
职责（确定性裁决，禁止 AI 参与）：
- 管理每个 NPC 的记忆版本链 V1→V2→V3 与删除段；
- 区分 layer: said（口供，可被编辑）/ heart（心声，加密）；
- 解锁（记忆修复 / 知识开导 / 条件线索）后向 Agent 层暴露 heart 层；
- 版本 diff 与两层矛盾自动产出「篡改点」tp_*（转线索卡入证据链）。

实现归 B 窗口。签名即契约：改动需回 A 窗口广播。
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MemoryBlock:
    id: str
    time: str
    layer: str            # "said" | "heart"
    text: str
    integrity: str        # "original" | "edited" | "deleted"


@dataclass
class MemoryVersion:
    owner: str
    version: int
    blocks: list[MemoryBlock] = field(default_factory=list)
    diff_from_prev: list[dict] = field(default_factory=list)


def _block_to_dict(b: MemoryBlock, version: int) -> dict:
    return {
        "id": b.id, "time": b.time, "layer": b.layer,
        "text": b.text, "integrity": b.integrity, "version": version,
    }


# 心声广播事故白名单词表：心声含任一案情词 → 禁播（防泄底，GAMEPLAY_V31 §四）
_BROADCAST_BLOCK_WORDS = ("删除", "监控", "芯片", "打卡", "接头", "水军", "篡改",
                          "权限", "记忆编辑", "仿冒", "备份")


class MemorySystem:
    def __init__(self) -> None:
        self._versions: dict[str, dict[int, MemoryVersion]] = {}
        self._unlocked: dict[str, int] = {}          # owner -> 当前对玩家解锁到的版本号
        self._heart_unlocked: set[str] = set()       # 心声层已解锁的 owner
        self._found_tps: set[str] = set()            # 已发现的篡改点 id（去重）
        self._tamper_points: list[dict] = []         # 按发现顺序
        self._tp_seq: dict[str, int] = {}            # owner -> 自动编号
        self._tp_used = 0                            # 已消耗篡改点（记忆拼图对质等）
        self._heart_unlock_count = 0                 # 心声层解锁次数（成就：偷听心声不犯法）
        self._puzzle_wins = 0                        # 拼图对质获胜次数（成就：时间线钉子户）
        self._event_log: list[dict] = []              # 记忆状态事件日志（可选诊断）
        self._heart_unlock_reasons: dict[str, set[str]] = {}

    # ------------------------------------------------------------------ load
    def load(self, scenario_dir: str) -> None:
        """加载 content/scenarios/kanshan/memory/ 下全部记忆文件。

        容错：目录不存在或为空时静默空载（内容组未交付不阻塞引擎单测）。
        """
        mem_dir = Path(scenario_dir) / "memory"
        self._versions = {}
        self._unlocked = {}
        self._heart_unlocked = set()
        self._event_log = []
        if not mem_dir.is_dir():
            return
        for f in sorted(mem_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            owner = data.get("owner")
            version = int(data.get("version", 0))
            if not owner or version <= 0:
                continue
            blocks = [
                MemoryBlock(
                    id=str(b["id"]), time=str(b.get("time", "")),
                    layer=str(b.get("layer", "said")),
                    text=str(b.get("text", "")),
                    integrity=str(b.get("integrity", "original")),
                )
                for b in data.get("blocks", [])
            ]
            mv = MemoryVersion(owner=owner, version=version, blocks=blocks,
                               diff_from_prev=list(data.get("diff_from_prev", [])))
            self._versions.setdefault(owner, {})[version] = mv
        # 初始解锁版本 = 每个 owner 的最低版本（V1 默认暴露）
        for owner, vs in self._versions.items():
            self._unlocked[owner] = min(vs)

    # --------------------------------------------------------------- version
    def current_version(self, char_id: str) -> int:
        """该 NPC 当前对玩家暴露的记忆版本号（未加载 / 未知角色返回 0）。"""
        return int(self._unlocked.get(char_id, 0))

    def _next_version(self, char_id: str) -> int | None:
        vs = self._versions.get(char_id)
        if not vs:
            return None
        cur = self._unlocked.get(char_id, min(vs))
        higher = [v for v in vs if v > cur]
        return min(higher) if higher else None

    # --------------------------------------------------------------- unlock
    def unlock_next(self, char_id: str, reason: str) -> dict:
        """解锁下一版本（reason: memory_fix | counsel | clue_condition）。

        成功返回 {"status": "ok", "unlocked_version", "revealed_blocks", "tamper_points"}；
        无更高版本或角色无记忆时返回 {"status": "no_op", ...}（同键结构，值为空）。
        解锁同时开启该角色心声层（heart 层此后可对 Agent 注入）。
        """
        nxt = self._next_version(char_id)
        if nxt is None:
            return {"status": "no_op", "unlocked_version": self.current_version(char_id),
                    "revealed_blocks": [], "tamper_points": [], "reason": "no_higher_version"}
        cur = self._unlocked.get(char_id, 0)
        self._unlocked[char_id] = nxt
        self._heart_unlocked.add(char_id)  # 心声层随版本解锁开启
        self._heart_unlock_reasons.setdefault(char_id, set()).add(str(reason or "unknown"))
        self._event_log.append({"type": "memory_unlock", "char_id": char_id,
                                "version": nxt, "reason": str(reason or "unknown")})
        self._heart_unlock_count += 1
        mv = self._versions[char_id][nxt]

        revealed = [_block_to_dict(b, nxt) for b in mv.blocks]
        tps: list[dict] = []
        # 篡改点来源 1：版本 diff（V>=2 才有）
        for i, diff in enumerate(mv.diff_from_prev):
            tp_id = diff.get("tamper_point") or self._auto_tp_id(char_id, nxt)
            desc = diff.get("change", f"第 {nxt} 版记忆与上一版存在出入")
            tp = self._make_tp(tp_id, char_id, nxt, "version_diff",
                               diff.get("block", ""), "", desc)
            if tp:
                tps.append(tp)
        # 篡改点来源 2：口供层被编辑且存在对应心声层 → 两层矛盾
        for b in mv.blocks:
            if b.layer == "said" and b.integrity == "edited":
                heart = self._paired_heart(mv, b)
                desc = (f"口供层与心声层矛盾：said「{b.text}」 vs heart「{heart.text if heart else '（缺失）'}」")
                tp = self._make_tp(self._auto_tp_id(char_id, nxt), char_id, nxt,
                                   "said_heart_conflict", b.id, b.time, desc)
                if tp:
                    tps.append(tp)
            # 篡改点来源 3：整段被删除的记忆
            elif b.integrity == "deleted":
                desc = f"该角色在 {b.time} 前后有一段记忆被整段删除（{b.text}）"
                tp = self._make_tp(self._auto_tp_id(char_id, nxt), char_id, nxt,
                                   "deleted_segment", b.id, b.time, desc)
                if tp:
                    tps.append(tp)
        return {"status": "ok", "unlocked_version": nxt, "reason": reason,
                "revealed_blocks": revealed, "tamper_points": tps}

    def _paired_heart(self, mv: MemoryVersion, said: MemoryBlock) -> MemoryBlock | None:
        base = said.id[:-1] if said.id.endswith("h") else said.id
        for b in mv.blocks:
            if b.layer == "heart" and (b.id == base + "h" or b.id == base or b.time == said.time):
                return b
        return None

    def _auto_tp_id(self, owner: str, version: int) -> str:
        n = self._tp_seq.get(owner, 0) + 1
        self._tp_seq[owner] = n
        return f"tp_{owner}_v{version}_{n}"

    def _make_tp(self, tp_id: str, owner: str, version: int, source: str,
                 block_id: str, time: str, desc: str) -> dict | None:
        if tp_id in self._found_tps:
            return None
        self._found_tps.add(tp_id)
        tp = {
            "id": tp_id, "owner": owner, "version": version, "source": source,
            "block_id": block_id, "time": time, "description": desc,
            # 自动转线索卡（新 clue schema，交给 evidence_chain.ingest_clue 入池）
            "clue_card": {
                "id": f"clue_{tp_id}",
                "name": f"篡改点：{owner} 的记忆出入",
                "tier": "hidden",
                "location": "记忆深处",
                "tags": ["记忆", "篡改", owner, time],
                "fact": desc,
                "flavor_hint": "描写心声与口供对不上的那一瞬间的违和感。",
                "linked_truth_nodes": [],
                "unlock_condition": "默认",
                "fake_of": None,
                "flaw_id": None,
            },
        }
        self._tamper_points.append(tp)
        return tp

    # --------------------------------------------------------------- visible
    def visible_blocks(self, char_id: str, include_heart: bool = False) -> list[MemoryBlock]:
        """Agent 层可注入的记忆块；heart 层仅在解锁后 include。"""
        vs = self._versions.get(char_id)
        if not vs:
            return []
        cur = self._unlocked.get(char_id, min(vs))
        blocks: list[MemoryBlock] = []
        for v in sorted(vs):
            if v > cur:
                continue
            for b in vs[v].blocks:
                if b.layer == "heart" and (not include_heart or char_id not in self._heart_unlocked):
                    continue
                blocks.append(b)
        return blocks

    # --------------------------------------------------------------- tamper
    def tamper_points(self) -> list[dict]:
        """已发现的篡改点（自动转证据链）。"""
        return list(self._tamper_points)

    # ---------------------------------------- P1 心声广播事故（白名单防泄底）
    def broadcast_accident(self, candidates: list[str] | None = None) -> dict:
        """心声广播事故（P1）：随机一名 NPC 的心声被全房广播 5 秒——
        **只播无案情心声**（白名单词表过滤，防泄底），欢乐名场面。

        candidates: 候选 NPC（缺省=全部已加载角色，须心声已解锁）。
        返回 {"ok", "char_id", "block", "text"} 或
        {"ok": False, "reason": "all_case_sensitive"|"no_unlocked_heart"}。
        """
        pool = [c for c in (candidates or sorted(self._versions))
                if c in self._heart_unlocked]
        if not pool:
            return {"ok": False, "reason": "no_unlocked_heart"}
        safe: list[tuple[str, MemoryBlock]] = []
        for char_id in pool:
            for b in self.visible_blocks(char_id, include_heart=True):
                if b.layer != "heart" or b.integrity == "deleted":
                    continue
                if not any(w in b.text for w in _BROADCAST_BLOCK_WORDS):
                    safe.append((char_id, b))
        if not safe:
            return {"ok": False, "reason": "all_case_sensitive",
                    "note": "本轮候选心声全部含案情信息，白名单拦下——DM 改播档案局广播体操。"}
        char_id, block = safe[self._tp_seq.get("__bc__", 0) % len(safe)]
        self._tp_seq["__bc__"] = self._tp_seq.get("__bc__", 0) + 1
        return {"ok": True, "char_id": char_id, "block": _block_to_dict(block, self.current_version(char_id)),
                "text": block.text, "note": "白名单校验通过：无案情信息，欢乐播送 5 秒。"}

    # ---------------------------------------- P2 记忆拼图对质
    def tamper_available(self) -> int:
        """可用篡改点数 = 已发现 - 已消耗（发起拼图对质需 2 个）。"""
        return max(0, len(self._tamper_points) - self._tp_used)

    def spend_tamper_points(self, n: int = 2) -> bool:
        """消耗篡改点（拼图对质发起成本）；不足返回 False。"""
        if self.tamper_available() < n:
            return False
        self._tp_used += n
        return True

    def puzzle_answer(self, char_id: str) -> list[str]:
        """记忆拼图正确答案：该角色当前已解锁全部记忆块按时间排序的 id 序列
        （同刻保持版本顺序）。引擎侧权威答案，前端投票比对用。"""
        blocks = self.visible_blocks(char_id, include_heart=True)
        ordered = sorted(enumerate(blocks), key=lambda t: (t[1].time, t[0]))
        return [b.id for _, b in ordered]

    def puzzle_judge(self, char_id: str, proposal: list[str]) -> dict:
        """记忆拼图对质结算：全场排出正确时间线——排对全场获线索、排错被锐评
        （线索奖励由上层经 evidence_chain 发放）。"""
        answer = self.puzzle_answer(char_id)
        correct = list(proposal) == answer
        if correct:
            self._puzzle_wins += 1
        return {"correct": correct, "answer": answer,
                "note": "排对全场获线索；排错进入 DM 锐评环节。"}

    # ------------------------------------------------- 成就判定数据源（只读）
    def heart_unlock_reasons(self, char_id: str | None = None) -> dict | set:
        """返回心声解锁原因；不传角色时返回副本，避免外部修改内部状态。"""
        if char_id is not None:
            return set(self._heart_unlock_reasons.get(char_id, set()))
        return {k: set(v) for k, v in self._heart_unlock_reasons.items()}

    def event_log(self, limit: int | None = None) -> list[dict]:
        """返回记忆状态事件日志副本（深拷贝，嵌套结构与外层隔离），可选限制最近条数。"""
        rows = self._event_log if limit is None else self._event_log[-max(0, int(limit)):]
        return [copy.deepcopy(item) for item in rows]

    def heart_unlock_count(self) -> int:
        """心声层解锁累计次数（成就：偷听心声不犯法 ≥5）。"""
        return self._heart_unlock_count

    def puzzle_wins(self) -> int:
        """拼图对质获胜次数（成就：时间线钉子户）。"""
        return self._puzzle_wins
