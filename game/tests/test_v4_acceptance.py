"""G6 验收：V4 综艺化新功能用例（docs/V4_SHOWTIME.md 规格）。

五组覆盖：
1. 大圆桌视图数据 —— rt（AgentRuntime）组装的演出结构（§二：席位环形布局 +
   发言聚光灯；A 裁决 9 席修正版 = 1 DM + 8 NPC；阵营零透出铁律）；
2. 综艺阶段事件 —— case_intro / act_transition / first_vote（§一 流程编排，
   G3 engine_driver 事件流）；
3. AgentRuntime 知识注入 —— agents/knowledge/*.md 存在且被 bridge 加载
   （注入 NPC system prompt；§三 知识库层）；
4. 跨幕记忆摘要 —— 幕结算钩子后 rt.memory_doc 非空（§三 记忆文档层）；
5. 机制幕门控 —— 破冰期 skill 返回 locked 事件、actSet 随 stage 推进 1→3
   （G3 已交付，锁定现行为）。

并行交付纪律（G6 验收约定）：功能面完全缺失时 skip（标记「未交付」，不算回归
失败，定性时按各组 STATUS 单独报告）；功能面已出现则从严断言（失败 = 真缺陷）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import GAME_ROOT, SCENARIO_DIR

pytestmark = pytest.mark.v4

KNOWLEDGE_DIR = GAME_ROOT / "agents" / "knowledge"
SKILLS_DIR = GAME_ROOT / "agents" / "skills"

# A 广播的 9 席修正版：上 1 DM + 8 NPC（玩家区不算席位）
DM_ID = "dm"
NPC_COUNT = 8

VARIETY_EVENTS = {"case_intro", "act_transition", "first_vote"}

# G4 交付中，接口名未定 → 探测候选（rt 方法名）
_ROUNDTABLE_CANDIDATES = (
    "roundtable_view", "round_table_view", "roundtable_data",
    "roundtable_flow", "roundtable_show", "roundtable_seats",
    "roundtable_snapshot", "roundtable", "table_view",
)


def _norm(text: str) -> str:
    """归一化匹配：去空白与 markdown 前缀噪声，避免格式差异误报。"""
    return "".join(str(text).split()).lstrip("-*#>").lstrip("-*#")


def _ev_name(event: dict) -> str:
    """事件名：优先 payload.event（driver 线），退回 type（契约 §3.6 线）。"""
    payload = event.get("payload") or {}
    return str(payload.get("event") or event.get("type") or "")


def _ev_dump(obj, depth: int = 0, seen: frozenset = frozenset()) -> str:
    """递归串化对象属性（探测注入痕迹用；限深防爆栈，跳过模块/可调用）。"""
    if depth > 4 or id(obj) in seen:
        return ""
    if isinstance(obj, str):
        return obj + "\n"
    if isinstance(obj, (int, float, bool)) or obj is None:
        return ""
    if isinstance(obj, dict):
        return "".join(_ev_dump(v, depth + 1, seen | {id(obj)}) for v in obj.values())
    if isinstance(obj, (list, tuple, set)):
        return "".join(_ev_dump(v, depth + 1, seen | {id(obj)}) for v in obj)
    if hasattr(obj, "__dict__"):
        return "".join(_ev_dump(v, depth + 1, seen | {id(obj)})
                       for v in vars(obj).values())
    return ""


@pytest.fixture()
def rt(tmp_path):
    from agents.bridge import AgentRuntime
    from agents.llm_client import LLMClient

    return AgentRuntime(llm=LLMClient(cache_dir=tmp_path / "agents_cache"))


# ================================================================ 1. 大圆桌视图
class TestRoundtableView:
    def _view_fn(self, rt):
        for name in _ROUNDTABLE_CANDIDATES:
            fn = getattr(rt, name, None)
            if callable(fn):
                return name, fn
        return None, None

    def test_rt_assembles_roundtable_view(self, rt):
        name, fn = self._view_fn(rt)
        if not name:
            pytest.skip("AgentRuntime 尚未提供大圆桌视图组装接口"
                        "（G1/G4 交付中；探测：" + "/".join(_ROUNDTABLE_CANDIDATES) + "）")
        view = fn()
        assert isinstance(view, dict), f"圆桌视图应为 dict，实得 {type(view)}"
        # 席位集合（容忍 seats/seating/players 多口径命名）
        seats = None
        for key in ("seats", "seat_list", "seating", "players", "positions"):
            if isinstance(view.get(key), list) and view[key]:
                seats = view[key]
                break
        assert seats, f"圆桌视图缺少席位列表（keys={sorted(view)}）"
        ids = [str(s.get("id") or s.get("char_id") or s.get("role") or "")
               for s in seats if isinstance(s, dict)]
        assert sum(1 for i in ids if i == DM_ID) == 1, \
            f"应有且仅有 1 个 DM 席（ids={ids}）"
        assert sum(1 for i in ids if i.startswith("char_")) == NPC_COUNT, \
            f"应有 {NPC_COUNT} 个 NPC 席（9 席修正版；ids={ids}）"
        # 阵营暗置铁律（CONTRACTS §四.4）：席位结构零 faction
        for s in seats:
            assert "faction" not in s, f"席位 {s.get('id')} 透出 faction 字段"
        dump = json.dumps(view, ensure_ascii=False, default=str)
        assert "faction" not in dump, "圆桌视图 JSON 透出 faction 字样"

    def test_roundtable_speaker_spotlight_shape(self, rt):
        """发言机制：当前发言者聚光（speaker/focus 字段）——出现则校验结构。"""
        name, fn = self._view_fn(rt)
        if not name:
            pytest.skip("大圆桌视图接口未交付（G1/G4）")
        view = fn()
        speaker = view.get("speaker") or view.get("focus") or view.get("current_speaker")
        if speaker is None:            # 规格允许默认空场（无人发言）
            return
        assert isinstance(speaker, (str, dict)), "speaker 应为 id 或席位结构"


# ================================================================ 2. 综艺阶段事件
class TestVarietyStageEvents:
    def test_case_intro_act_transition_first_vote(self, fresh_driver):
        driver, sid = fresh_driver()
        session = driver.create_session("main", session_id=sid)
        seen: set[str] = set()
        found: dict[str, dict] = {}

        def collect(evs):
            for e in evs or []:
                n = _ev_name(e)
                seen.add(n)
                found.setdefault(n, e)

        collect(session.get("events", []))
        # 破冰（case_intro 应在此：DM 分三段讲案情）→ 搜证 → 圆桌
        for _ in range(2):
            evs, err = driver.apply_action(session, "advance", "player:1", {})
            assert err is None, err
            collect(evs)
        assert session["stage"] == "round_table", \
            f"两次 advance 后应到圆桌幕，实得 {session['stage']}"
        # ⑥ 第一次指认：圆桌内快速举手表决（不影响结局）
        evs, err = driver.apply_action(session, "vote", "player:1",
                                       {"target": "char_01"})
        assert err is None, err
        collect(evs)
        assert session["status"] == "playing", "圆桌预投票不得终局（不影响结局）"
        # 第三幕转场（act_t3 热搜风暴前）
        evs, err = driver.apply_action(session, "advance", "player:1", {})
        assert err is None, err
        collect(evs)

        missing = VARIETY_EVENTS - seen
        if missing == VARIETY_EVENTS:
            pytest.skip("综艺阶段事件三件（case_intro/act_transition/first_vote）"
                        "均未在事件流中出现（G3 未交付或口径不同）")
        assert not missing, \
            f"综艺阶段事件部分缺失：{sorted(missing)}（已见：{sorted(seen & VARIETY_EVENTS)}）"
        # 事件结构：事件名出现在 payload.event 或 type；payload 非空
        for n in VARIETY_EVENTS:
            e = found[n]
            payload = e.get("payload") or {}
            assert payload, f"{n} 事件 payload 为空"

    def test_first_vote_not_affecting_ending(self, fresh_driver):
        """first_vote（圆桌举手）只喂弹幕梗，不得触发终局结算。"""
        driver, sid = fresh_driver()
        session = driver.create_session("main", session_id=sid)
        for _ in range(2):
            driver.apply_action(session, "advance", "player:1", {})
        evs, err = driver.apply_action(session, "vote", "player:1",
                                       {"target": "char_02"})
        assert err is None, err
        assert not any(_ev_name(e) == "ending" for e in evs), \
            "圆桌预投票触发了 ending 结算（违反「不影响结局」规格）"


# ================================================================ 3. 知识注入
class TestKnowledgeInjection:
    def test_knowledge_files_exist(self):
        if not KNOWLEDGE_DIR.is_dir():
            pytest.skip("agents/knowledge/ 目录未交付（G4 并行交付中）")
        mds = sorted(KNOWLEDGE_DIR.glob("*.md"))
        assert mds, "agents/knowledge/ 存在但无 .md 知识文档"
        assert len(mds) >= NPC_COUNT, \
            f"知识文档 {len(mds)} 份 < 8 NPC 人设知识文档规格"
        for f in mds:
            text = f.read_text(encoding="utf-8").strip()
            assert len(text) >= 50, f"{f.name} 内容过短（{len(text)} 字符），疑占位"

    def test_knowledge_covers_all_npcs(self, rt):
        if not KNOWLEDGE_DIR.is_dir():
            pytest.skip("agents/knowledge/ 目录未交付（G4）")
        corpus = "\n".join(
            f.read_text(encoding="utf-8") for f in KNOWLEDGE_DIR.glob("*.md"))
        missing = [cid for cid in rt.npcs if cid not in corpus
                   and (rt.npcs[cid].character.get("name") or "") not in corpus]
        assert not missing, f"知识文档未覆盖角色：{missing}"

    def test_bridge_loads_knowledge_into_prompt(self, rt):
        """「被 bridge 加载」实证：知识文档标志性文本出现在 rt/npc 注入面。"""
        if not KNOWLEDGE_DIR.is_dir():
            pytest.skip("agents/knowledge/ 目录未交付（G4）")
        checked = 0
        for f in KNOWLEDGE_DIR.glob("*.md"):
            # 取文档中最长的一行作为标志片段（标题/金句级，避开目录噪声）
            lines = [ln.strip() for ln in
                     f.read_text(encoding="utf-8").splitlines()]
            lines = [ln for ln in lines if len(ln) >= 12]
            if not lines:
                continue
            frag = max(lines, key=len)
            injected = (_norm(frag) in _norm(_ev_dump(rt))) or any(
                _norm(frag) in _norm(_ev_dump(npc))
                or _norm(frag) in _norm(npc._render_system(trust=50))
                for npc in rt.npcs.values())
            assert injected, \
                f"知识文档 {f.name} 的标志文本未被 bridge/NPC 注入面加载：{frag[:40]}…"
            checked += 1
        assert checked, "agents/knowledge/*.md 均无可提取的标志文本"


# ================================================================ 4. 跨幕记忆摘要
class TestCrossActMemoryDoc:
    def test_memory_doc_after_act_settle(self, rt):
        """幕结算（settle_act）后 memory_doc 非空：char_id → [{act, summary}]。"""
        if not hasattr(rt, "memory_doc") or not callable(
                getattr(rt, "settle_act", None)):
            pytest.skip("AgentRuntime.memory_doc / settle_act 未交付（G4 并行交付中）")
        rt.record_act_event("测试事件：破冰幕收尾")
        res = rt.settle_act(1)
        assert res.get("summary", "").strip(), "settle_act 返回摘要为空"
        assert res.get("injected"), "settle_act 未注入任何 NPC"
        doc = rt.memory_doc
        assert isinstance(doc, dict) and doc, "memory_doc 应为非空 dict"
        for cid, entries in doc.items():
            assert cid in rt.npcs, f"memory_doc 出现未知角色 {cid}"
            assert entries and entries[-1]["act"] == 1, f"{cid} 幕条目缺失"
            s = str(entries[-1]["summary"]).strip()
            assert s, f"{cid} 摘要为空"
            assert len(s) <= 200, f"{cid} 摘要超 200 字规格（{len(s)}）"
        # 摘要含本幕流水要点（record_act_event 登记的事件进入权威底稿）
        any_summary = doc[next(iter(doc))][-1]["summary"]
        assert "测试事件" in any_summary or "第1幕" in any_summary, \
            f"摘要未包含本幕关键事件：{any_summary[:60]}"

    def test_memory_doc_injected_into_npc_prompt(self, rt):
        """下一幕注入：结算后 NPC system 模板含跨幕记忆块（marker 围栏）。"""
        if not hasattr(rt, "memory_doc") or not callable(
                getattr(rt, "settle_act", None)):
            pytest.skip("AgentRuntime.memory_doc / settle_act 未交付（G4）")
        assert not any("<<<CROSS_ACT_MEMORY>>>" in npc.system
                       for npc in rt.npcs.values()), "结算前不应有跨幕记忆块"
        rt.settle_act(1)
        rt.settle_act(2, notes=["第二幕要点：不在场证明对质"])
        marker = "<<<CROSS_ACT_MEMORY>>>"
        for cid, npc in rt.npcs.items():
            assert marker in npc.system, f"{cid} system 模板缺跨幕记忆块"
            assert "第1幕" in npc.system and "第2幕" in npc.system, \
                f"{cid} 跨幕记忆未覆盖两幕摘要"
            assert "不在场证明对质" in npc.system, \
                f"{cid} notes 要点未进入注入块"

    def test_memory_doc_same_act_idempotent(self, rt):
        """同幕重复结算幂等：覆盖同幕条目，不追加重复记录。"""
        if not hasattr(rt, "memory_doc") or not callable(
                getattr(rt, "settle_act", None)):
            pytest.skip("AgentRuntime.memory_doc / settle_act 未交付（G4）")
        rt.settle_act(1)
        cid = next(iter(rt.npcs))
        n1 = len(rt.memory_doc[cid])
        rt.settle_act(1)
        assert len(rt.memory_doc[cid]) == n1, "同幕重复结算追加了重复条目"
        rt.settle_act(2)
        assert len(rt.memory_doc[cid]) == n1 + 1, "跨幕结算未追加新条目"
        assert [e["act"] for e in rt.memory_doc[cid]] == [1, 2]


# ================================================================ 5. 机制幕门控
class TestMechanismActGating:
    def test_icebreaker_skill_locked(self, fresh_driver):
        """破冰期（act 1）skill 被门控：白名单拒绝（引擎裁决）或 locked 事件，
        且任何机制不得实际执行。"""
        driver, sid = fresh_driver()
        session = driver.create_session("main", session_id=sid)
        assert session["stage"] == "break_ice"
        for skill in ("refute", "buy_heat", "memory_fix", "truth_check"):
            evs, err = driver.apply_action(session, "skill", "player:1",
                                           {"skill": skill})
            if err is not None:
                # 门控层①：阶段白名单拒绝（sm.can("skill")=False，引擎裁决）
                assert "不允许动作" in err and "skill" in err, \
                    f"skill={skill} 的拒绝理由非阶段门控：{err}"
                # 门控层②：_do_skill 引擎分支的 locked 事件存在（纵深防御）
                evs2 = driver._do_skill(session, "player:1", {"skill": skill})
                assert evs2 and evs2[0].get("payload", {}).get("event") == "locked", \
                    f"skill={skill} 引擎侧缺 locked 分支事件（events={[_ev_name(e) for e in evs2]}）"
                assert "破冰" in str(evs2[0]["payload"].get("notice", "")), \
                    "locked 事件应说明破冰期门控原因"
            else:
                locked = [e for e in evs
                          if (e.get("payload") or {}).get("event") == "locked"]
                assert locked, \
                    f"破冰阶段 skill={skill} 未被门控（events={[_ev_name(e) for e in evs]}）"
                assert "破冰" in str(locked[0]["payload"].get("notice", ""))
            # 门控兜底：无论哪层拦截，机制不得实际执行
            if err is None:
                assert not any(_ev_name(e) in ("refute_result", "buy_heat_result",
                                               "memory_unlock", "heat_report")
                               for e in evs), f"skill={skill} 在破冰期被实际执行"

    def test_skill_unlocked_after_icebreaker(self, fresh_driver):
        """搜证幕（act 2）起门控解除：truth_check 正常返回热度报告。"""
        driver, sid = fresh_driver()
        session = driver.create_session("main", session_id=sid)
        driver.apply_action(session, "advance", "player:1", {})
        assert session["stage"] == "investigate"
        evs, err = driver.apply_action(session, "skill", "player:1",
                                       {"skill": "truth_check"})
        assert err is None, err
        assert not any((e.get("payload") or {}).get("event") == "locked" for e in evs), \
            "搜证幕 skill 仍被 locked 门控（现行为：仅破冰期锁定）"

    def test_actset_advances_1_to_4(self, fresh_driver):
        """actSet 对齐前端三章：破冰/搜证=1（地图仍在），圆桌=2，指认=3。"""
        driver, sid = fresh_driver()
        session = driver.create_session("main", session_id=sid)
        # 建局即破冰幕（act 1，ACT_NOW 口径）
        assert session["stage"] == "break_ice"
        pairs: list[tuple[str, int]] = []
        for _ in range(3):
            evs, err = driver.apply_action(session, "advance", "player:1", {})
            assert err is None, err
            for e in evs:
                p = e.get("payload") or {}
                if p.get("event") == "stage_changed":
                    pairs.append((str(p.get("stage")), int(p.get("actSet", -1))))
        assert pairs == [("investigate", 1), ("round_table", 2), ("accuse", 3)], \
            f"actSet 推进序列不符：{pairs}"
        # 末幕幂等：accuse 再 advance 不再产出 stage_changed（actSet 不越界）
        evs, err = driver.apply_action(session, "advance", "player:1", {})
        assert err is None, err
        assert not any((e.get("payload") or {}).get("event") == "stage_changed"
                       for e in evs), "末幕后仍产出 stage_changed（actSet 越界）"
