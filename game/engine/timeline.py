"""时间线引擎：案发时间线的查询与证词校验。

数据源：content/scenarios/kanshan/timeline.json（结构同 template/timeline.json）。
规则：NPC 的证词若与时间线冲突，一致性守卫必须拦截。

V3 升级：
- lie_points：抽取标注「说谎点」的轨迹条目（NPC 起初隐瞒的关键行动）；
- check_claims：批量校验一组「时间-地点」主张，返回逐条一致性明细；
- trace_conflicts：将 NPC 记忆块（said 层）与时间线对照，输出冲突列表
  （供 memory_system 篡改点交叉验证，纯确定性）。

旧骨架签名与语义保留：__init__ / query / verify / public_entries。
"""
import json
from pathlib import Path


class Timeline:
    def __init__(self, scenario_dir: Path):
        data = json.loads((Path(scenario_dir) / "timeline.json").read_text(encoding="utf-8"))
        self.entries = data["timeline"]
        self.rules = data.get("rules", {})

    # -------------------------------------------------------------- 旧骨架 API
    def query(self, character: str, time_range=None) -> list:
        """查询某角色在指定时间段的行动轨迹（NPC 记忆检索用）。"""
        entries = [e for e in self.entries if e["character"] == character]
        if time_range:
            lo, hi = time_range
            entries = [e for e in entries if lo <= e["time"] <= hi]
        return entries

    def verify(self, character: str, time: str, location: str) -> bool:
        """校验证词中的'时间-地点'是否与时间线一致。"""
        for e in self.entries:
            if e["character"] == character and e["time"] == time:
                return e["location"] == location
        return True  # 未覆盖的时间点不拦截（宽容）

    def public_entries(self) -> list:
        """公开时间线（复盘阶段展示）。"""
        return [e for e in self.entries if e.get("public", False)]

    # ------------------------------------------------------------------ V3 新增
    def lie_points(self, character: str) -> list[dict]:
        """该角色标注了「说谎点」的轨迹条目（NPC 起初隐瞒、可被证据戳穿）。"""
        return [dict(e) for e in self.entries
                if e["character"] == character and "说谎点" in str(e.get("action", ""))]

    def check_claims(self, character: str, claims: list[dict]) -> list[dict]:
        """批量校验一组「时间-地点」主张（证词拦截用，纯确定性）。

        claims: [{"time": "21:00", "location": "茶水间"}, ...]
        返回逐条明细 {"time", "location", "consistent", "actual_location"}；
        时间线未覆盖该时刻 → consistent=True（宽容，与 verify 语义一致）。
        """
        results = []
        for c in claims:
            t, loc = str(c.get("time", "")), str(c.get("location", ""))
            actual = None
            for e in self.entries:
                if e["character"] == character and e["time"] == t:
                    actual = e["location"]
                    break
            consistent = True if actual is None else (actual == loc)
            results.append({"time": t, "location": loc, "consistent": consistent,
                            "actual_location": actual})
        return results

    def trace_conflicts(self, character: str, memory_blocks: list[dict]) -> list[dict]:
        """NPC said 层记忆块 vs 时间线对照：输出冲突（篡改点交叉验证）。

        memory_blocks: [{"id", "time", "layer", "text", ...}, ...]（只看 said 层）。
        时间线中该角色在该时刻的真实地点与记忆块文本中出现的地点名不符 → 冲突。
        文本地点匹配为包含式关键词匹配（确定性，不调 AI）。
        """
        conflicts = []
        timeline = {e["time"]: e for e in self.entries if e["character"] == character}
        for b in memory_blocks:
            if str(b.get("layer", "said")) != "said":
                continue
            t = str(b.get("time", ""))
            entry = timeline.get(t)
            if not entry:
                continue
            # 时间线同刻地点名未在记忆文本中出现，且文本里提到了另一个已知地点 → 可疑
            loc = str(entry.get("location", ""))
            text = str(b.get("text", ""))
            if loc and loc not in text:
                for other in {e["location"] for e in self.entries if e.get("location")}:
                    if other and other != loc and other in text:
                        conflicts.append({
                            "character": character, "time": t,
                            "timeline_location": loc,
                            "claimed_location": other, "block_id": b.get("id", ""),
                            "note": f"时间线 {t} 应在「{loc}」，记忆却提到「{other}」"})
                        break
        return conflicts
