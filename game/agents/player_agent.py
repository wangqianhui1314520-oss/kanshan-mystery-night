"""按闭卷决策下一步动作（AI 坐席 / 自走棋）。

先走 play_hints 启发式（零 LLM，测试与无 key 可跑）；
有 gateway 时再让模型在合法动作里挑，失败回退启发式。
Agent 只提议，裁决仍走引擎 apply_action。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

try:
    from .llm_client import call_gateway, read_prompt
except ImportError:
    from llm_client import call_gateway, read_prompt

try:
    from .consistency_guard import ConsistencyGuard
except ImportError:
    try:
        from consistency_guard import ConsistencyGuard
    except ImportError:
        ConsistencyGuard = None

from engine.booklet import BookletLibrary, load_library, stage_to_chapter
try:
    from .agent_state import AgentState, rank_actions, validate_action
except ImportError:
    from agent_state import AgentState, rank_actions, validate_action

try:
    from engine.stage_machine import legal_actions as _engine_legal_actions
except ImportError:
    _engine_legal_actions = None

# 坐席可提议的动作全集（再与阶段表 / 调用方 legal 求交）
LEGAL = (
    "chat", "introduce", "search", "private_chat", "skill", "counsel",
    "reveal_clue", "vote", "accuse", "advance", "review",
)
_ICE_FORBIDDEN = frozenset({"search", "vote", "accuse"})
_STAGE_LEGAL_FALLBACK = {
    "break_ice": ("chat", "introduce", "advance"),
    "investigate": ("chat", "search", "private_chat", "skill", "counsel", "advance"),
    "round_table": ("chat", "reveal_clue", "private_chat", "skill", "counsel",
                    "vote", "advance"),
    "accuse": ("accuse", "vote", "advance"),
    "review": ("review",),
}
_PUBLIC_KEYS = ("type", "payload", "source", "role_id", "chapter", "reason")
_FACTION_KEYS = frozenset({"faction", "faction_label"})
_FACTION_LITERALS = (
    "faction", "faction_label", "pollution", "swayable",
    "污染", "求真", "摇摆", "阵营",
)
_JSON_RE = re.compile(r"\{.*\}", re.S)
_QUOTED_RE = re.compile(r"[『「]([^『「』」]+)[』」]")
_SPLIT_BAN = re.compile(r"[、，。；：:！？!?\|/——–\n]+")
_NEVER_SUFFIX = re.compile(r"(这个词|这两个字|二字)$")
_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _loads_json_loose(raw: str):
    """从模型输出里取出第一个完整 JSON 对象，容忍尾部多余字符。

    实测：部分模型（如知乎直答 zhida-agent）会在合法 JSON 后再补一个 `}`，
    贪婪正则 `\\{.*\\}` 会把多余括号一起吞掉，json.loads 直接失败，
    导致整条 LLM 决策链静默回落启发式。改用 raw_decode 在第一个完整
    对象处收口，多余尾部自然忽略。
    """
    if not raw:
        return None
    dec = json.JSONDecoder()
    i = raw.find("{")
    while 0 <= i < len(raw):
        try:
            obj, _ = dec.raw_decode(raw, i)
        except ValueError:
            i = raw.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            return obj
        i = raw.find("{", i + 1)
    return None


_STAGE_TACTIC = {
    "break_ice": "优先自我介绍与对话，禁止搜证",
    "investigate": "优先 search 去地点搜证；拿到线索后再发言",
    "round_table": "优先出示线索、开导或技能；可 vote",
    "accuse": "只能指认或投票",
    "review": "只做复盘",
}


def _slim_user(pack: dict, hints: dict, stage, allowed: list) -> str:
    """精简版决策上下文（PLAYER_ACT_SLIM=1 时启用）。

    只喂关键字段：角色 / 人设 / 腔调 / 本轮任务 / 硬禁 / 合法动作。
    千字级闭卷全文会让部分检索型模型出戏（实测知乎直答会改播自我介绍），
    精简后实测 3/3 稳定产出角色化 JSON。
    """

    def _cut(v, n: int) -> str:
        return str(v or "")[:n]

    cover = {}
    for letter in ("C", "B", "A"):
        c = (pack.get("covers") or {}).get(letter)
        if c:
            cover = c
            break
    return json.dumps({
        "stage": _stage_key(stage),
        "legal": list(allowed),
        "角色": pack.get("name") or pack.get("role_id"),
        "人设": _cut(cover.get("you_are"), 60),
        "说话风格": _cut(hints.get("chat_style"), 40),
        "本轮任务": _cut(cover.get("task"), 60),
        "不能说": list(hints.get("must_not") or [])[:4],
        "阶段策略": _STAGE_TACTIC.get(_stage_key(stage), ""),
        "要求": "一句台词，符合人设与腔调，不超过 40 字",
    }, ensure_ascii=False)


def _stage_key(stage) -> str:
    return str(getattr(stage, "value", stage) or "break_ice")


def _stage_legal(stage) -> frozenset[str]:
    if _engine_legal_actions is not None:
        return frozenset(_engine_legal_actions(stage))
    return frozenset(_STAGE_LEGAL_FALLBACK.get(_stage_key(stage), ("chat",)))


def _narrow_legal(stage, legal: list[str] | None) -> list[str]:
    """阶段表收窄超集；再与 LEGAL / 传入 legal 求交。默认去掉 advance。"""
    stage_set = _stage_legal(stage)
    incoming = {a for a in (legal if legal is not None else LEGAL) if a in LEGAL}
    allowed = [a for a in LEGAL if a in stage_set and a in incoming]
    if _stage_key(stage) == "break_ice":
        allowed = [a for a in allowed if a not in _ICE_FORBIDDEN]
    playable = [a for a in allowed if a != "advance"]
    if playable:
        return playable
    return allowed or ["chat"]


def _public_decision(act: dict) -> dict:
    """对外只留动作字段，剥离 faction / faction_label。"""
    raw = dict(act or {})
    out = {k: raw[k] for k in _PUBLIC_KEYS if k in raw}
    payload = dict(out.get("payload") or raw.get("payload") or {})
    for key in list(payload):
        if key in _FACTION_KEYS or "faction" in str(key).lower():
            payload.pop(key, None)
    out["payload"] = payload
    for key in list(out):
        if key in _FACTION_KEYS or "faction" in str(key).lower():
            out.pop(key, None)
    return out


def _only_advance(allowed: list[str]) -> bool:
    return bool(allowed) and all(a == "advance" for a in allowed)


def _held_cards(state: dict) -> list:
    return list((state or {}).get("held_cards") or [])


def _held_cards_empty(state: dict) -> bool:
    return not _held_cards(state)


def _first_card_id(held) -> str:
    if not held:
        return ""
    first = held[0]
    if isinstance(first, dict):
        return str(first.get("id") or first.get("card") or first.get("kc_id") or "")
    return str(first)


def _is_swayable(pack: dict, state: dict) -> bool:
    if (state or {}).get("swayable") is True:
        return True
    return pack.get("faction") == "swayable"


def _cover_bans(pack: dict, hints: dict | None = None) -> list[str]:
    """pack.covers[*].never_say 与 must_not 的字面（含标点切分）。"""
    phrases: list[str] = []
    hints = hints or {}
    for cover in (pack.get("covers") or {}).values():
        if not isinstance(cover, dict):
            continue
        ns = str(cover.get("never_say") or "").strip()
        if ns:
            phrases.append(ns)
            for part in _SPLIT_BAN.split(ns):
                part = part.strip(" 「」『』\"'")
                if len(part) < 2:
                    continue
                phrases.append(part)
                stripped = _NEVER_SUFFIX.sub("", part).strip()
                if len(stripped) >= 2:
                    phrases.append(stripped)
        for item in ((cover.get("play_hints") or {}).get("must_not") or []):
            item = str(item or "").strip()
            if item:
                phrases.append(item)
    for item in hints.get("must_not") or []:
        item = str(item or "").strip()
        if item:
            phrases.append(item)
    uniq: list[str] = []
    seen: set[str] = set()
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase not in seen:
            seen.add(phrase)
            uniq.append(phrase)
    return uniq


def _safe_intro(pack: dict) -> str:
    name = pack.get("name") or "我"
    return f"我是{name}。今晚先认识一下。"


def _scrub_chat(text: str, pack: dict, hints: dict | None = None) -> str:
    """去掉 never_say / must_not 字面；守卫再拦一层，违规则回安全自我介绍。"""
    text = str(text or "")
    bans = _cover_bans(pack, hints)
    for phrase in bans:
        if phrase and phrase in text:
            text = text.replace(phrase, "")
    text = re.sub(r"[，。、；]{2,}", "。", text)
    text = re.sub(r"\s+", " ", text).strip(" ，。、；")
    if ConsistencyGuard is not None and text:
        try:
            guard = ConsistencyGuard(None, None, {})
            if guard.check({}, text, {"must_not_say": bans}):
                text = _safe_intro(pack)
        except Exception:
            pass
    if not text:
        text = _safe_intro(pack)
    for phrase in bans:
        if phrase and phrase in text:
            text = text.replace(phrase, "")
    return text.strip(" ，。、；") or "先认识一下。"


def _ice_line(pack: dict, hints: dict | None = None) -> str:
    """破冰自我介绍：带 play_hints.chat_style，并滤禁语。"""
    hints = hints or {}
    style = str(hints.get("chat_style") or "").strip()
    if not style:
        cover_a = (pack.get("covers") or {}).get("A") or {}
        style = str(((cover_a.get("play_hints") or {}).get("chat_style") or "")).strip()
    name = pack.get("name") or "我"
    raw = f"我是{name}。{style}" if style else _safe_intro(pack)
    return _scrub_chat(raw, pack, hints)


def _chat_payload(pack: dict, hints: dict, target: str) -> dict:
    return {"text": _ice_line(pack, hints), "target": target, "char_id": target}


def _skill_section(text: str, title: str) -> str:
    m = re.search(rf"##\s*{re.escape(title)}.*?(?=\n##\s|\Z)", text or "", re.S)
    return m.group(0) if m else ""


def _first_spoken(block: str) -> str:
    if not block:
        return ""
    for m in _QUOTED_RE.finditer(block):
        line = (m.group(1) or "").strip()
        if len(line) >= 4:
            return line
    for raw in block.splitlines():
        s = re.sub(r"^\s*\d+[\.、]\s*", "", raw).strip()
        s = re.sub(r"^[^：:]{1,12}[：:]", "", s).strip()
        s = s.strip("『』「」\"'")
        if len(s) >= 8 and not s.startswith(("#", ">", "-")):
            return s
    return ""


def _skill_line(role_id: str) -> str:
    """读 npc_{role_id}.md：示例台词，否则第一条句式。没有文件则空串。"""
    rid = str(role_id or "").strip()
    if not rid:
        return ""
    path = _SKILLS_DIR / f"npc_{rid}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    line = _first_spoken(_skill_section(text, "示例台词"))
    if not line:
        line = _first_spoken(_skill_section(text, "句式模板"))
    if not line:
        return ""
    if any(tok and tok in line for tok in _FACTION_LITERALS):
        return ""
    return line


def _skill_lines(role_id: str) -> list[str]:
    rid = str(role_id or "").strip()
    if not rid:
        return []
    path = _SKILLS_DIR / f"npc_{rid}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    block = _skill_section(text, "示例台词") or _skill_section(text, "句式模板")
    out: list[str] = []
    for m in _QUOTED_RE.finditer(block or ""):
        line = (m.group(1) or "").strip()
        if len(line) < 4:
            continue
        if any(tok and tok in line for tok in _FACTION_LITERALS):
            continue
        if line not in out:
            out.append(line)
    return out


def _table_line(pack: dict, hints: dict, tick: int, human_text: str = "") -> str:
    lines = _skill_lines(pack.get("role_id"))
    if lines:
        return _scrub_chat(lines[int(tick or 0) % len(lines)], pack, hints)
    if human_text.strip():
        name = pack.get("name") or "我"
        return _scrub_chat(f"我是{name}。听见了，我按自己的本接着查。", pack, hints)
    return _ice_line(pack, hints)


def _whisper_line(pack: dict, hints: dict) -> str:
    name = pack.get("name") or "我"
    return _scrub_chat(
        f"这句只给你——我是{name}。桌上那些我先不说满，你要问的我私下答。",
        pack, hints)


class PlayerAgent:
    def __init__(self, library: BookletLibrary, gateway=None):
        self.library = library
        self.gateway = gateway

    @classmethod
    def from_scenario(cls, scenario_dir: Path | str, gateway=None) -> "PlayerAgent":
        return cls(load_library(scenario_dir), gateway=gateway)

    def decide(self, role_id: str, *, stage: str = "break_ice",
               legal: list[str] | None = None, state: dict | None = None,
               use_llm: bool = True) -> dict:
        chapter = stage_to_chapter(stage)
        pack = self.library.visible_pack(role_id, chapter, include_faction=True)
        hints = self.library.merged_hints(role_id, chapter)
        allowed = _narrow_legal(stage, legal)
        state = state or {}
        agent_state = AgentState.from_dict({**state, "stage": _stage_key(stage)})
        heuristic = self._heuristic(pack, hints, stage, allowed, state)
        ok, _ = validate_action(heuristic, allowed, agent_state)
        if not ok:
            # 让启发式也服从同一协议，避免产生空卡牌/无证据投票；
            # 投票 payload 保留原目标（引擎侧仍会按 mode 校验证据卡）。
            heuristic["payload"] = {
                **(heuristic.get("payload") or {}),
                "evidence": list(agent_state.evidence or []),
            }
        if use_llm and self.gateway is not None:
            try:
                llm = self._llm_decide(pack, hints, stage, allowed, state)
            except Exception:
                llm = None
            valid, _ = validate_action(llm or {}, allowed, agent_state)
            if (llm and valid
                    and not (llm.get("type") == "advance" and not _only_advance(allowed))):
                llm.setdefault("source", "llm")
                llm.setdefault("role_id", pack["role_id"])
                llm.setdefault("chapter", chapter)
                return _public_decision(llm)
        heuristic["source"] = "heuristic"
        agent_state.remember(str(heuristic.get("type") or "chat"))
        heuristic["role_id"] = pack["role_id"]
        heuristic["chapter"] = chapter
        return _public_decision(heuristic)

    def _heuristic(self, pack: dict, hints: dict, stage: str,
                   allowed: list[str], state: dict) -> dict:
        prefer = [a for a in (hints.get("prefer_actions") or []) if a in allowed
                  and a != "advance"]
        locs = hints.get("search_locations") or []
        kws = hints.get("search_keywords") or ["线索"]
        others = [c for c in (state.get("other_chars") or [])
                  if c and c != pack.get("role_id")]
        target = others[0] if others else ""
        held = _held_cards(state)
        tick = int(state.get("seat_tick") or 0)
        human_text = str(state.get("last_human_text") or "")
        host = str(state.get("host_id") or "")
        key = _stage_key(stage)

        def talk(text: str, *, whisper: bool = False, reason: str = "按本发言") -> dict:
            payload = {"text": text, "target": target, "char_id": target}
            if whisper and host:
                payload["whisper"] = True
                payload["to"] = host
            return {"type": "chat", "payload": payload,
                    "reason": "私下递一句" if whisper else reason}

        if key == "break_ice":
            lines = _skill_lines(pack.get("role_id"))
            text = (lines[tick % len(lines)] if lines
                    else _ice_line(pack, hints))
            if "chat" in allowed:
                return talk(_scrub_chat(text, pack, hints), reason="破冰自我介绍")
            if "introduce" in allowed:
                return {"type": "introduce",
                        "payload": _chat_payload(pack, hints, target),
                        "reason": "封A破冰：自我介绍"}
            if _only_advance(allowed):
                return {"type": "advance", "payload": {}, "reason": "仅剩推进"}
            return talk(_ice_line(pack, hints), reason="破冰兜底")

        if key == "investigate":
            step = tick % 4
            if step == 3 and host and "chat" in allowed:
                return talk(_whisper_line(pack, hints), whisper=True)
            # 状态特化优先于轮转：手上有开导卡就立刻用掉（测试契约 §booklet）。
            if held and "counsel" in allowed and target:
                return {"type": "counsel",
                        "payload": {"card": _first_card_id(held),
                                    "target": target, "char_id": target},
                        "reason": "有卡则开导"}
            if step == 0 and "search" in allowed and locs:
                loc = locs[tick % len(locs)]
                kw = kws[tick % len(kws)] if kws else "线索"
                return {"type": "search",
                        "payload": {"location": loc, "keyword": kw},
                        "reason": f"按本搜证：去{loc}搜{kw}"}
            if "skill" in allowed and (step == 2 or "search" not in allowed):
                skill = "draw_card" if not held else "truth_check"
                return {"type": "skill", "payload": {"skill": skill},
                        "reason": "搜证抽卡或鉴真"}
            if "chat" in allowed:
                return talk(_table_line(pack, hints, tick, human_text))

        if key == "round_table":
            step = tick % 3
            # 状态特化优先：圆桌可开技能时 step0/1 均优先技能，只有 step2 且持卡才开导。
            if "skill" in allowed and step in (0, 1):
                skill = ("memory_fix" if pack.get("role_kind") == "investigator"
                         else "draw_card")
                payload = {"skill": skill}
                if skill == "memory_fix" and target:
                    payload["target"] = target
                if ("defect" in (state.get("open_skills") or [])
                        and _is_swayable(pack, state)):
                    payload = {"skill": "defect", "char_id": pack["role_id"]}
                return {"type": "skill", "payload": payload,
                        "reason": "圆桌按本用技能"}
            if step == 2 and held and "counsel" in allowed and target:
                return {"type": "counsel",
                        "payload": {"card": _first_card_id(held),
                                    "target": target, "char_id": target},
                        "reason": "圆桌开导"}
            if host and tick % 4 == 3 and "chat" in allowed:
                return talk(_whisper_line(pack, hints), whisper=True)
            if "chat" in allowed:
                return talk(_table_line(pack, hints, tick, human_text))

        if key in ("accuse", "review") and "vote" in allowed:
            vote_to = state.get("vote_target") or target or "char_01"
            evidence = list(state.get("evidence") or [])[:2]
            return {"type": "vote",
                    "payload": {"target": vote_to, "evidence": evidence},
                    "reason": "终局按本指认"}

        if prefer:
            act = prefer[0]
            if act == "search" and locs:
                return {"type": "search",
                        "payload": {"location": locs[0], "keyword": kws[0]},
                        "reason": "闭卷 prefer search"}
            if act == "skill" and "skill" in allowed:
                skill = "draw_card" if _held_cards_empty(state) else "truth_check"
                return {"type": "skill", "payload": {"skill": skill},
                        "reason": "闭卷 prefer skill"}
            if act == "counsel" and held and target:
                return {"type": "counsel",
                        "payload": {"card": _first_card_id(held),
                                    "target": target, "char_id": target},
                        "reason": "闭卷 prefer counsel"}
            if act == "chat":
                return talk(_table_line(pack, hints, tick, human_text),
                            reason="闭卷 prefer chat")
        if "chat" in allowed:
            return talk(_table_line(pack, hints, tick, human_text))
        if _only_advance(allowed):
            return {"type": "advance", "payload": {}, "reason": "仅剩推进"}
        fallback = next((a for a in allowed if a != "advance"), "chat")
        return {"type": fallback, "payload": {}, "reason": "兜底合法动作"}

    def _llm_decide(self, pack: dict, hints: dict, stage: str,
                    allowed: list[str], state: dict) -> dict | None:
        try:
            try:
                system = read_prompt("player_act.md")
            except OSError:
                system = "只输出 JSON：{type,payload,reason}"
            # 精简模式：部分检索型模型（如知乎直答）面对千字级闭卷正文会出戏，
            # 只喂关键字段 + 强身份约束才能稳定产出决策 JSON。默认关闭。
            slim = os.environ.get("PLAYER_ACT_SLIM", "0") not in (
                "0", "", "false", "False")
            if slim:
                system += ("\n\n铁律：禁止介绍自己，禁止提及 AI / 搜索 / 助手身份；"
                           "你只扮演闭卷里指定的角色，只输出决策 JSON。")
            skill_md = ""
            try:
                skill_md = (_SKILLS_DIR / f"npc_{pack.get('role_id')}.md").read_text(
                    encoding="utf-8")
            except OSError:
                skill_md = ""
            others = [c for c in (state.get("other_chars") or [])
                      if c and c != pack.get("role_id")]
            user = json.dumps({
                "stage": _stage_key(stage),
                "legal": allowed,
                "booklet": self.library.agent_prompt(pack["role_id"], pack["chapter"]),
                "skill": skill_md,
                "hints": hints,
                "never_say": _cover_bans(pack, hints),
                "state": {
                    "ap": state.get("ap"),
                    "other_chars": others,
                    "held_clues": state.get("held_clues") or [],
                    "held_cards": state.get("held_cards") or [],
                    "evidence": list(state.get("evidence") or [])[:2],
                    "open_skills": state.get("open_skills") or [],
                    "seat_tick": state.get("seat_tick") or 0,
                    "last_human_text": (state.get("last_human_text") or "")[:80],
                },
            }, ensure_ascii=False)
            if slim:
                user = _slim_user(pack, hints, stage, allowed)
            raw = str(call_gateway(self.gateway, system, user, temperature=0.3))
            data = _loads_json_loose(raw)
            if not isinstance(data, dict) or data.get("type") not in allowed:
                return None
            if data.get("type") == "advance" and not _only_advance(allowed):
                return None
            payload = dict(data.get("payload") or {})
            typ = data.get("type")
            if typ in ("chat", "introduce"):
                # 实测部分模型把台词放在 content / line 字段，统一容错
                said = (payload.get("text") or payload.get("content")
                        or payload.get("line") or "")
                payload["text"] = _scrub_chat(str(said), pack, hints)
            elif typ == "search":
                locs = hints.get("search_locations") or []
                kws = hints.get("search_keywords") or ["线索"]
                payload.setdefault("location", locs[0] if locs else "")
                payload.setdefault("keyword", kws[0] if kws else "线索")
            elif typ == "counsel":
                held = _held_cards(state)
                if held and not payload.get("card"):
                    payload["card"] = _first_card_id(held)
                if others and not payload.get("target"):
                    payload["target"] = others[0]
            elif typ == "vote":
                payload["evidence"] = list(
                    payload.get("evidence") or state.get("evidence") or [])[:2]
            data["payload"] = payload
            for key in list(data):
                if key in _FACTION_KEYS or "faction" in str(key).lower():
                    data.pop(key, None)
            for key in list(data["payload"]):
                if key in _FACTION_KEYS or "faction" in str(key).lower():
                    data["payload"].pop(key, None)
            return data
        except Exception:
            return None
