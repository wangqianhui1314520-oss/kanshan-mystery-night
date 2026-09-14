"""segments_lib — D 组演出文案资产加载器（scripts/segments_p1.md / segments_p2.md /
achievements.md）。

职责（确定性，零 AI）：
- 解析 segments_p1.md：抽风错误惩罚池（原句→重写句）、故障播报池、押注结算句、
  急诊室红灯播报/NPC 状态词/抢救追加句、心声广播事故白名单池、头条竞标模板/话题池/成败句；
- 解析 segments_p2.md：广播台整点播报池/点播名场面/事故彩蛋、快问快答 20 题题库、
  反诈剧场三幕剧本与结算句；
- 解析 achievements.md：23 项成就库（id/名/稀有度/条件 JSON/横幅文案/分享卡句），
  §三 引擎对接 JSON 为判定条件权威来源，§一/§二 表格为横幅文案权威来源。
容错：文件缺失/格式漂移 → 对应池为空，调用方回落内置兜底（演出不断流）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _clean(cell: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(cell or "").strip().strip("`"))


def _strip_d(self, x):  # pragma: no cover（占位防误用）
    raise NotImplementedError


def _rows_of_table(section_text: str) -> list[list[str]]:
    """提取 markdown 表格行（| 分割），去掉表头分隔行。"""
    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def _list_items(section_text: str) -> list[str]:
    """提取小节内 `- ` / `* ` 列表项（清理引用符号）。"""
    out = []
    for line in section_text.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m:
            out.append(_clean(m.group(1)))
    return out


class SegmentsLibrary:
    def __init__(self, scripts_dir: Path | str):
        self.dir = Path(scripts_dir)
        self.p1 = self._read("segments_p1.md")
        self.p2 = self._read("segments_p2.md")
        self.ach_md = self._read("achievements.md")
        self.minis = self._read("minis.md")

        # ---------------- P1 ----------------
        self.glitch_pairs = self._parse_glitch_pairs()          # [(原句, 重写句)]
        self.glitch_banners = self._section_list(self.p1, "抽风系统故障播报池")
        self.bet_lines = self._parse_bet_lines()                # {open, win, lose}
        self.red_alert_template = self._red_alert_template()
        self.rescue_words = self._parse_rescue_words()          # {npc: (状态词, 追加句)}
        self.rescue_success_line = self._first_contains(self.p1, "抢救成功演出", "【叮——抢救成功")
        self.broadcast_accident_pool = self._parse_accident_pool()
        self.broadcast_poke = self._first_contains(self.p1, "心声广播事故", "DM 补刀")
        self.headline_open_template = self._first_contains(self.p1, "竞标主持词", "本轮头条位开标")
        self.headline_result_template = self._first_contains(self.p1, "竞标主持词", "本轮头条由")
        self.headline_topics = self._parse_headline_topics()    # [(话题, is_fun)]
        self.headline_result_lines = self._parse_headline_results()

        # ---------------- P2 ----------------
        self.radio_reports = self._section_list(self.p2, "整点播报模板")
        self.radio_performances = self._section_list(self.p2, "点播名场面预设")
        self.radio_accidents = self._section_list(self.p2, "广播事故彩蛋")
        self.quiz_bank = self._parse_quiz_bank()                # [ {question, options, answer, taunt} ]
        self.antifraud_acts = self._parse_antifraud_acts()      # [(幕名, 剧本全文)]
        self.antifraud_settle = self._parse_antifraud_settle()

        # ---------------- 成就库 ----------------
        self.achievement_conditions = self._parse_achievement_json()
        self.achievement_banners = self._parse_achievement_banners()
        self.achievements = self._merge_achievements()

        # ---------------- M4 侦探花名池（minis.md，成就锐评花名来源） ----------------
        self.headline_pool = self._parse_headline_pool()   # [(花名, [关键词], 介绍)]

        # ---------------- M2 心声窃听器题库（minis.md；F memory-puzzle 路由数据源） --
        self.heart_quiz_bank = self._parse_heart_quiz_bank()  # [{tier,npc,said,heart,answer,teaching}]
        self.heart_quiz_settle = self._parse_heart_quiz_settle()  # {win, lose, outro}

    def _parse_headline_pool(self) -> list[tuple[str, list[str], str]]:
        """minis.md §M4：22 个欢乐警衔（headline 关键词匹配，无命中走通用档）。"""
        sec = self._section(self.minis, "侦探花名池")
        pool = []
        for row in _rows_of_table(sec):
            if len(row) >= 4 and re.fullmatch(r"\d{1,2}", _clean(row[0]) or ""):
                kws = [k.strip() for k in re.split(r"[/、,，]", _clean(row[2])) if k.strip()]
                pool.append((_clean(row[1]), kws, _clean(row[3])))
        return pool

    def pick_headline(self, headline_text: str = "",
                      seed: int = 0) -> tuple[str, str]:
        """依玩家知乎 headline 关键词匹配警衔（M4 机制：无命中从池底通用档抽）。

        返回 (花名, 一句话介绍)。minis.md 缺失时返回 (见习侦探, "")。"""
        text = str(headline_text or "")
        for name, kws, intro in self.headline_pool:
            if any(k and k in text for k in kws):
                return name, intro
        if self.headline_pool:
            name, _kws, intro = self.headline_pool[seed % len(self.headline_pool)]
            return name, intro
        return "见习侦探", ""

    # ------------------------------------------------------------ M2 心声窃听器
    def _parse_heart_quiz_bank(self) -> list[dict]:
        """minis.md §M2：双层记忆教学题（tier=open 免登录脱敏 / full 仅登录局内）。
        列结构：#/tier/NPC/口供(said)/心声(heart)/答案位/教学点。"""
        sec = self._section(self.minis, "心声窃听器题库")
        bank = []
        for row in _rows_of_table(sec):
            if len(row) >= 7 and re.fullmatch(r"\d{1,2}", _clean(row[0]) or ""):
                bank.append({
                    "tier": _clean(row[1]) or "open",
                    "npc": _clean(row[2]),
                    "said": _clean(row[3]),
                    "heart": _clean(row[4]),
                    "answer": _clean(row[5]).strip().upper()[-1:] or "B",
                    "teaching": _clean(row[6]),
                })
        return bank

    def heart_quiz_pool(self, tier: str = "open") -> list[dict]:
        """F 的 GET /api/minis/memory-puzzle 数据源：按 tier 过滤（open=脱敏抽样），
        洗牌后返回题面（said/heart/answer/npc）；full 题永不进未登录池。"""
        import random as _r
        pool = [dict(q) for q in self.heart_quiz_bank if q.get("tier") == tier]
        _r.Random(f"{tier}|{len(pool)}").shuffle(pool)
        return pool

    def _parse_heart_quiz_settle(self) -> dict[str, str]:
        """结算句三连：答对/答错/热身关收尾（§M2 内 `- ` 行，无子标题）。"""
        sec = self._section(self.minis, "心声窃听器题库")
        items = _list_items(sec)
        return {
            "win": next((x for x in items if "窃听成功" in x), ""),
            "lose": next((x for x in items if "嘴硬版" in x), ""),
            "outro": next((x for x in items if "接下来一整幕" in x), ""),
        }

    # -------------------------------------------------------------- 基础
    def _read(self, name: str) -> str:
        try:
            return (self.dir / name).read_text(encoding="utf-8")
        except OSError:
            return ""

    def _section(self, doc: str, heading_keyword: str) -> str:
        """按标题关键词截取小节（到下一个同级/更高级标题为止）。"""
        if not doc:
            return ""
        lines = doc.splitlines()
        start = next((i for i, ln in enumerate(lines)
                      if re.match(r"^#{2,4}\s", ln) and heading_keyword in ln), None)
        if start is None:
            return ""
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^#{1,4}\s", lines[i]) and i > start), len(lines))
        return "\n".join(lines[start:end])

    def _section_list(self, doc: str, heading_keyword: str) -> list[str]:
        return _list_items(self._section(doc, heading_keyword))

    def _first_contains(self, doc: str, heading_keyword: str, needle: str) -> str:
        items = self._section_list(doc, heading_keyword)
        return next((x for x in items if needle in x), "")

    # -------------------------------------------------------------- P1
    def _parse_glitch_pairs(self) -> list[tuple[str, str]]:
        sec = self._section(self.p1, "惩罚池")          # D v2：§1.1 惩罚池（抽风句→重写句）
        pairs = []
        for row in _rows_of_table(sec):
            if len(row) >= 3 and row[1].startswith("【惩罚"):
                pairs.append((_clean(row[1]), _clean(row[2])))
        return pairs

    def _parse_bet_lines(self) -> dict[str, str]:
        sec = self._section(self.p1, "弹幕押注结算句")
        return {
            "open": next((x for x in _list_items(sec) if "押注通道开启" in x), ""),
            "win": next((x for x in _list_items(sec) if "眼光毒辣" in x), ""),
            "lose": next((x for x in _list_items(sec) if "押错了" in x), ""),
        }

    def _red_alert_template(self) -> str:
        sec = self._section(self.p1, "病情恶化播报")
        return next((x for x in _list_items(sec) if "急诊警报" in x), "")

    def _parse_rescue_words(self) -> dict[str, tuple[str, str]]:
        sec = self._section(self.p1, "各 NPC 红灯专属状态词")
        out: dict[str, tuple[str, str]] = {}
        for row in _rows_of_table(sec):
            if len(row) >= 3 and row[0] and _clean(row[0]) != "NPC":
                out[_clean(row[0])] = (_clean(row[1]), _clean(row[2]))
        return out

    def _parse_accident_pool(self) -> list[str]:
        """心声广播事故白名单池：D v2 §2.5 为引号包裹的嵌套列表行（每行一句）。"""
        sec = self._section(self.p1, "心声广播事故")
        out = []
        for line in (sec or "").splitlines():
            m = re.match(r'^[ \t]*[-*][ \t]*[“"](.+?)[”"][，。]?[ \t]*$', line)
            if m and len(m.group(1)) >= 6:
                out.append(m.group(1))
        return out

    def _parse_headline_topics(self) -> list[tuple[str, bool]]:
        """话题池：兼容单行编号串与列表行（D 组 §3.3 为一行 1.-8.）。"""
        sec = self._section(self.p1, "头条位话题池")
        topics = []
        for chunk in re.split(r"(?=\d+[.、]\s*《)", sec or ""):
            m = re.search(r"《(.+?)》", chunk)
            if not m:
                continue
            is_fun = "纯欢乐位" in chunk or "不进热度结算" in chunk
            topics.append((m.group(1), is_fun))
        return topics

    def _parse_headline_results(self) -> dict[str, str]:
        sec = self._section(self.p1, "竞标失败/成功彩蛋句")
        items = _list_items(sec)
        return {
            "lose": next((x for x in items if "出价慢了" in x), ""),
            "win_truth": next((x for x in items if "头条归你，真相" in x), ""),
            "win_pollution": next((x for x in items if "截图存证" in x), ""),
        }

    # -------------------------------------------------------------- P2
    def _parse_quiz_bank(self) -> list[dict]:
        sec = self._section(self.p2, "快问快答题库")
        bank = []
        for row in _rows_of_table(sec):
            if len(row) >= 5 and re.fullmatch(r"\d{1,2}", _clean(row[0]) or ""):
                opts = [c for c in re.split(r"\s+(?=[ABC]\s)", _clean(row[2])) if c]
                opts = [re.sub(r"^[ABC]\s*", "", o) for o in opts] or [_clean(row[2])]
                ans_letter = (_clean(row[3]) or "A").strip()[-1].upper()
                idx = max(0, ord(ans_letter) - ord("A"))
                bank.append({
                    "question": _clean(row[1]),
                    "options": opts,
                    "answer_text": opts[idx] if idx < len(opts) else opts[0],
                    "taunt": _clean(row[4]),
                })
        return bank

    def _parse_antifraud_acts(self) -> list[tuple[str, str]]:
        acts = []
        for kw in ("第一幕", "第二幕", "第三幕"):
            sec = self._section(self.p2, kw)
            if sec:
                title = next((ln.strip(" #") for ln in sec.splitlines()
                              if kw in ln and ln.startswith("#")), kw)
                acts.append((_clean(title), sec))
        return acts

    def _parse_antifraud_settle(self) -> dict[str, str]:
        sec = self._section(self.p2, "结算句")
        items = _list_items(sec)
        return {
            "all_correct": next((x for x in items if "反诈学分" in x), ""),
            "wrong": next((x for x in items if "慌" in x), ""),
        }

    # -------------------------------------------------------------- 成就库
    def _parse_achievement_json(self) -> list[dict]:
        if not self.ach_md:
            return []
        m = re.search(r"```json\s*(\[.*?\])\s*```", self.ach_md, re.S)
        if not m:
            return []
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return []

    def _parse_achievement_banners(self) -> dict[str, dict]:
        """横幅文案来自 achievements.md 全文档表格行（D v2 §二「引擎同步总表」，
        列结构与 v1 一致：id/成就/稀有度/条件/横幅文案/分享卡句）。"""
        out: dict[str, dict] = {}
        for row in _rows_of_table(self.ach_md):
            if len(row) >= 6 and row[0].strip().startswith("ach_"):
                out[_clean(row[0])] = {
                    "name": _clean(row[1]),
                    "rarity": _clean(row[2]),
                    "banner": _clean(row[4]),
                    "share_line": _clean(row[5]),
                }
        return out

    def _merge_achievements(self) -> list[dict]:
        merged = []
        for cond in self.achievement_conditions:
            extra = self.achievement_banners.get(cond.get("id"), {})
            merged.append({
                "id": cond.get("id"),
                "name": extra.get("name") or cond.get("name", cond.get("id")),
                "rarity": extra.get("rarity") or cond.get("rarity", "bronze"),
                "condition": cond.get("condition", {}),
                "banner": extra.get("banner", ""),
                "share_line": extra.get("share_line", ""),
            })
        return merged


_RARITY_ORDER = {"egg": 0, "bronze": 1, "silver": 2, "gold": 3}


def rarity_rank(rarity: str) -> int:
    return _RARITY_ORDER.get(str(rarity).lower(), 1)
