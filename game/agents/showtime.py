"""showtime — 演出导演：侦探报告 / 成就 / P1·P2 演出位 / 防卡死备忘录。

v2（对齐 D 组文案资产）：演出生成按 `content/scenarios/kanshan/scripts/`
segments_p1.md / segments_p2.md 文案池与句式驱动（segments_lib.SegmentsLibrary
确定性解析）；成就判定/文案以 `achievements.md` 为权威（23 项：§三 JSON=条件，
§一/§二 表格=横幅文案模板+分享卡句）。AI 只做个性化锐评（横幅文案+玩家
headline 花名），池缺失或 LLM 失败一律回落 D 组文案/内置兜底，演出不断流。

铁律（segments 硬规则）：所有环节台词不进证据链、不改 fact；泄底词禁用；
广播事故只播白名单无案情心声；快问快答不给出新证据。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

try:
    from .llm_client import call_gateway, fallback_text, read_prompt
    from .segments_lib import SegmentsLibrary, rarity_rank
except ImportError:                          # 直接以脚本方式运行
    from llm_client import call_gateway, fallback_text, read_prompt
    from segments_lib import SegmentsLibrary, rarity_rank

DEFAULT_SCRIPTS_DIR = (Path(__file__).resolve().parent.parent
                       / "content" / "scenarios" / "kanshan" / "scripts")


class ShowtimeDirector:
    """演出位生成器（挂载于 AgentRuntime.show）。"""

    def __init__(self, llm=None, scripts_dir: Path | str = DEFAULT_SCRIPTS_DIR):
        self.llm = llm
        self.segments = SegmentsLibrary(scripts_dir)
        self._quiz_seq = 0
        self._glitch_seq = 0
        self._radio_seq = 0
        self._topic_seq = 0

    # ------------------------------------------------------------ 内部
    def _gen(self, kind: str, prompt_file: str, user: str,
             fallback_scene: str) -> str:
        system = read_prompt(prompt_file)
        user = f"演出位:{kind}\n{user}"
        try:
            out = str(call_gateway(self.llm, system, user)).strip()
        except Exception:
            out = ""
        return out or fallback_text(fallback_scene)

    # ================================================== P0 侦探报告（v2：消费引擎确定性判定）
    def detective_report(self, stats: dict, badges: list[str] | None = None,
                         engine_achievements: list[dict] | None = None,
                         highlights: list[str] | None = None) -> dict:
        """复盘页侦探报告（resolver.achievements() 徽章 + AchievementEngine 解锁）。

        铁律（GAMEPLAY_V31 §八裁决 #6）：badges 为引擎确定性判定结果，**原样进
        报告，LLM 不得增删改判**——AI 只做文笔润色；mock/失败时报告由确定性
        部分直接拼装（演出不断流）。返回 {report_text, badges, achievements}。"""
        badges = list(badges or [])
        engine_achievements = list(engine_achievements or [])
        highlights = list(highlights or [])
        badge_wall = "、".join(badges) if badges else "（本局无 MEGA 徽章）"
        user = (
            f"演出位说明：生成侦探报告。\n"
            f"session_no：{stats.get('session_no', '0713')}\n"
            f"stats_json：{json.dumps(self._safe_stats(stats), ensure_ascii=False)}\n"
            f"badges（resolver.achievements() 确定性徽章，原样转述、禁止增删改判）："
            f"{json.dumps(badges, ensure_ascii=False)}\n"
            f"engine_achievements（23 项 DSL 解锁，含横幅文案）："
            f"{json.dumps([{'id': a.get('id'), 'name': a.get('name'), 'banner': a.get('banner')}
                           for a in engine_achievements], ensure_ascii=False)}\n"
            f"highlights（高光操作回放，只可转述不得虚构）："
            f"{json.dumps(highlights, ensure_ascii=False)}")
        text = self._gen("detective_report", "showtime_report.md", user,
                         "show_detective_report")
        # 防改判校验：LLM 输出若吞掉徽章，直接以确定性拼装兜底（判定不改判）
        if badges and not all(b in text for b in badges):
            text = (f"叮——档案局 · 侦探报告 No.{stats.get('session_no', '0713')}\n"
                    f"推理评分与数据：以引擎统计为准（见 stats）。\n"
                    f"高光回放：{('；'.join(highlights) if highlights else '本局波澜不惊。')}\n"
                    f"人格化锐评：{text[:80]}\n"
                    f"成就徽章：{badge_wall}\n"
                    f"报告生成：Archiv3 v3.1｜复核：系统提示音（一切正常。）")
        return {"report_text": text, "badges": badges,
                "achievements": engine_achievements}

    # ================================================== 成就（achievements.md 权威）
    def achievement_show(self, achievement: dict,
                         player_headline: str = "见习侦探") -> dict:
        """成就解锁演出：横幅文案模板（D 组原样）+ AI 个性化锐评。

        锐评规格（achievements.md §三）：模板 = 横幅文案 + 玩家 headline 花名；
        生成失败/mock → 直接用横幅文案兜底（不为空、不虚构）。"""
        banner = achievement.get("banner") or ""
        user = (f"演出位说明：成就解锁锐评。\n"
                f"成就：{achievement.get('name', '')}\n"
                f"横幅文案（原样引用，可微调语气但不得改事实）：{banner}\n"
                f"玩家 headline 花名：{player_headline}\n"
                f"稀有度：{achievement.get('rarity', 'bronze')}")
        comment = self._gen("achievement_show", "showtime_report.md", user,
                            "show_achievement_show")
        show_text = (f"叮——成就解锁：【{achievement.get('name', '')}】\n"
                     f"{banner}\n{comment}")
        return {"id": achievement.get("id"), "name": achievement.get("name"),
                "rarity": achievement.get("rarity"),
                "banner": banner, "share_line": achievement.get("share_line", ""),
                "ai_comment": comment, "show": show_text}

    # ------------------------------------------------ 判定（确定性，achievements.md §三 JSON）
    def check_achievements(self, stats: dict, unlocked: set[str]) -> list[dict]:
        """对 23 项成就条件确定性求值，返回首次达成且未记录的成就（无副作用）。"""
        fresh = []
        for ach in self.segments.achievements:
            if ach["id"] in unlocked:
                continue
            try:
                if self._eval_condition(ach.get("condition", {}), stats):
                    fresh.append(ach)
            except Exception:
                continue
        # 稀有度高的先上台（gold/egg 优先）
        fresh.sort(key=lambda a: -rarity_rank(a.get("rarity")))
        return fresh

    @staticmethod
    def _eval_condition(cond: dict, stats: dict) -> bool:
        ctype = str(cond.get("type", ""))
        op = str(cond.get("op", ""))
        value = cond.get("value")
        target = cond.get("target")
        counters = stats.get("counters", {})
        if ctype == "ending":
            return str(value) in stats.get("endings", set())
        if ctype == "chat_keyword":
            return str(value) in stats.get("chat_keywords", set())
        if ctype == "env_clue":
            return any(str(value) in s for s in stats.get("env_clues_seen", set()))
        if ctype == "counsel_multi":
            got = stats.get("counsel_multi", {}).get(str(target), set())
            return set(cond.get("cards", [])) <= set(got)
        if ctype == "confrontation_win":
            return bool(counters.get(f"confrontation_win:{target}"))
        if ctype in ("memory_puzzle_win", "antifraud_all_correct",
                     "closing_vote_top1_survived"):
            return bool(counters.get(ctype))
        # 数值型：type 即统计键（counsel_count 走顶层，其余走 counters）
        actual = stats.get(ctype, counters.get(ctype, 0))
        actual = int(actual or 0)
        want = int(value if value is not None else 1)
        if op == ">=":
            return actual >= want
        if op == "==":
            return actual == want
        if op == "<=":
            return actual <= want
        return actual >= want                      # 无 op 默认 ≥1 存在性判定

    # ================================================== P1 演出位（segments_p1.md）
    def glitch_rewrite(self, banner: str) -> str:
        """抽风横幅重写：先精确/包含匹配 D 组重写句，未命中再 AI 仿写句式。"""
        for bad, good in self.segments.glitch_pairs:
            if bad == banner or (banner and banner in bad):
                return f"叮——检测到横幅输出异常。现更正：{good}"
        user = (f"演出位说明：抽风横幅重写。\nbanner：{banner}\n"
                f"句式参照（D 组池）：{[g for _, g in self.segments.glitch_pairs[:3]]}")
        return self._gen("glitch_rewrite", "showtime_p1.md", user,
                         "show_glitch_rewrite")

    def glitch_banner(self) -> str:
        """故障播报池（横幅乱码演出；每幕至多 2 次的频控归引擎，本方法只供文案）。"""
        pool = self.segments.glitch_banners
        if pool:
            self._glitch_seq += 1
            return pool[self._glitch_seq % len(pool)]
        return fallback_text("show_glitch_rewrite")

    def bet_settle(self, won: bool) -> str:
        """弹幕押注结算句（P1 配套，输赢由引擎/上层判定）。"""
        line = (self.segments.bet_lines.get("win" if won else "lose") or "").strip()
        return line or fallback_text("show_bet")

    def red_alert(self, char_name: str) -> str:
        """开导失败 → 心病恶化红灯播报（segments_p1 §2.1 模板）。"""
        if self.segments.red_alert_template:
            return self.segments.red_alert_template.replace("char_XX", str(char_name))
        return (f"叮——急诊警报：{char_name} 心病恶化，红灯亮起。"
                "下一轮内带对口知识卡抢救，收益翻倍。")

    def npc_red_state(self, char_name: str) -> str:
        """NPC 红灯专属状态词（AI 生成锚点，segments_p1 §2.3）。"""
        for npc, (state, _append) in self.segments.rescue_words.items():
            if npc in str(char_name):
                return state
        return ""

    def rescue_success(self, char_name: str) -> str:
        """抢救成功演出（双倍收益）+ 该 NPC 专属追加句（segments_p1 §2.2/2.3）。"""
        head = self.segments.rescue_success_line or "叮——抢救成功！双倍收益已到账。"
        extra = ""
        for npc, (_state, append) in self.segments.rescue_words.items():
            if npc in str(char_name):
                extra = append
                break
        return f"{head}" + (f"\n{extra}" if extra else "")

    def broadcast_accident(self, char_name: str = "", engine_result: dict | None = None) -> str:
        """心声广播事故 v3：白名单过滤权归引擎（memory.broadcast_accident——
        只播已解锁且无案情词的心声）；本方法只包装演出。

        engine_result=None 时回落 D 组白名单池（segments_p1 §2.4）。"""
        if engine_result is not None:
            if not engine_result.get("ok"):
                reason = engine_result.get("reason", "")
                if reason == "all_case_sensitive":
                    return ("叮——突发广播事故：候选心声全部含案情敏感词，"
                            "全部拦截。本系统临时改播：第八套广播体操，现在开始。")
                return ("叮——广播事故预警：尚无人解锁心声层，"
                        "本台暂无料可播——这是好消息，恭喜各位。")
            char_id = engine_result.get("char_id", "某位")
            text = str(engine_result.get("text", "")).strip()
            poke = self.segments.broadcast_poke.split("：", 1)[-1].strip() \
                if self.segments.broadcast_poke else ""
            return (f"叮——突发：{char_id} 的心声层信号串台，全房广播 5 秒。{text}"
                    + (f"\n{poke}" if poke else ""))
        pool = self.segments.broadcast_accident_pool
        if pool:
            line = random.Random(f"{char_name}|{len(pool)}").choice(pool)
            poke = ""
            if self.segments.broadcast_poke:
                poke = self.segments.broadcast_poke.split("：", 1)[-1].strip()
            who = f"{char_name} 的心声层信号串台" if char_name else "一段心声信号串台"
            return (f"叮——突发：{who}，全房广播 5 秒。{line}"
                    + (f"\n{poke}" if poke else ""))
        return self._gen("broadcast_accident", "showtime_p1.md",
                         f"演出位说明：广播事故。context：{char_name}",
                         "show_broadcast_accident")

    def memo_render(self, engine_memo: dict, gradient: str = "normal") -> dict:
        """「档案局备忘录」演出渲染：方向词与预算由 difficulty.memo_for 确定性
        给出（assist 2/幕、normal 1、hard 0），AI 仅润色语气——**不得增删方向
        信息**，润色失败直接用引擎原文（点方向不泄底）。"""
        base = str(engine_memo.get("text", "")).strip()
        hint = str(engine_memo.get("hint", ""))
        user = (f"演出位说明：档案局备忘录润色。\n"
                f"梯度：{gradient}\n"
                f"引擎原文（方向词「{hint}」必须原样保留）：{base}")
        text = self._gen(f"memo_{gradient}", "showtime_memo.md", user,
                         "show_memo_engine")
        if hint and hint not in text:
            text = base                               # 润色丢了方向词 → 用引擎原文
        return {"kind": "memorandum", "gradient": gradient,
                "hint": hint, "location": engine_memo.get("location", ""),
                "memo_text": text, "source": "difficulty_engine"}

    def collectibles_show(self, payload: dict) -> str:
        """鱼干收集品集齐演出：看山Bot 隐藏语音逐句排布（IndexTTS 2.5 按句切片
        不合并）+ 终极层加播段。内容以引擎 unlock_payload 为准，AI 不改写台词。"""
        lines = [str(x).strip() for x in (payload.get("voice_lines") or []) if str(x).strip()]
        extra = str(payload.get("boss_reveal_extra") or "").strip()
        if not lines:
            return fallback_text("show_collectibles")
        out = ["叮——检测到隐藏信号：三袋鱼干全部归位，看山Bot 的隐藏语音已解锁。"]
        out += [f"【看山Bot · 隐藏语音 {i}】{ln}" for i, ln in enumerate(lines, 1)]
        if extra:
            out.append(f"【终极层加播】{extra}")
        out.append("（语音按句切片逐句播放，不合并。）")
        return "\n".join(out)

    def headline_auction(self, topic: str | None = None) -> str:
        """头条竞标主持词（segments_p1 §3.1 模板填 §3.3 话题池；成交由引擎裁决）。"""
        if not topic:
            topics = [t for t, _fun in self.segments.headline_topics] or ["监控空洞之谜"]
            self._topic_seq += 1
            topic = topics[self._topic_seq % len(topics)]
        if self.segments.headline_open_template:
            return self.segments.headline_open_template.replace("___________", str(topic))
        return self._gen("headline_auction", "showtime_p1.md",
                         f"演出位说明：头条竞标主持。topic：{topic}",
                         "show_headline_auction")

    def headline_result(self, faction: str) -> str:
        """开标结果句：truth / pollution（segments_p1 §3.1 结果模板 + §3.4 彩蛋）。"""
        lines = self.segments.headline_result_lines
        if faction == "pollution":
            return lines.get("win_pollution") or lines.get("win_truth") or ""
        return lines.get("win_truth") or ""

    def headline_topics(self) -> list[tuple[str, bool]]:
        return list(self.segments.headline_topics)

    # ================================================== P2 演出位（segments_p2.md）
    def radio_station(self, round_no: int = 0, clue_count: int = 0,
                      spotlight: str | None = None) -> str:
        """广播台：整点播报池（封控时长/线索数填空）→ 点播名场面 → 偶发事故彩蛋。"""
        parts = []
        reports = self.segments.radio_reports
        if reports:
            self._radio_seq += 1
            text = reports[self._radio_seq % len(reports)]
            text = (text.replace("第 N 小时", f"第 {max(1, round_no)} 小时")
                        .replace("线索 N 条", f"线索 {clue_count} 条"))
            parts.append(text)
        if spotlight:
            hit = next((x for x in self.segments.radio_performances if spotlight in x), None)
            parts.append(hit or "")
        elif self.segments.radio_performances:
            parts.append(self.segments.radio_performances[
                self._radio_seq % len(self.segments.radio_performances)])
        if round_no and round_no % 2 == 0 and self.segments.radio_accidents:
            parts.append(self.segments.radio_accidents[
                self._radio_seq % len(self.segments.radio_accidents)])
        text = "\n".join(p for p in parts if p).strip()
        return text or self._gen("radio_station", "showtime_p2.md",
                                 "演出位说明：广播台节目。", "show_radio_station")

    def anti_fraud_theater(self, act: int = 1) -> str:
        """反诈剧场：D 组三幕剧本（act 1/2/3）。公益向，角色虚构。"""
        acts = self.segments.antifraud_acts
        if acts:
            title, script = acts[(max(1, act) - 1) % len(acts)]
            return f"【{title}】\n{script}".strip()
        return self._gen("anti_fraud_theater", "showtime_p2.md",
                         f"演出位说明：反诈剧场第 {act} 幕。", "show_anti_fraud_theater")

    def antifraud_settle(self, all_correct: bool) -> str:
        settle = self.segments.antifraud_settle
        return ((settle.get("all_correct") if all_correct else settle.get("wrong"))
                or "")

    def puzzle_show(self, result: dict, char_name: str = "") -> str:
        """记忆拼图对质演出（segments_p2 语义：排对全场获线索 / 排错 DM 锐评）。"""
        if result.get("correct"):
            return (f"叮——拼图对质完成：{char_name or '该角色'} 的深夜轨迹被全场"
                    "一秒排平。时间线钉子户上线，全场奖励一条线索！（引擎已登记）")
        return (f"叮——拼图对质失败：{char_name or '该角色'} 的深夜被排成了"
                "悬疑片。锐评：时间不会说谎，但你们会。（排错进入 DM 锐评环节）")

    def hammer_announce(self, most_hammered: str | None,
                        name_map: dict | None = None) -> str:
        """「最想锤的人」宣布（分池结果，不影响指认；投票前不透阵营）。"""
        if not most_hammered:
            return "叮——「最想锤的人」投票平票。全员安全的夜晚，反而有点不习惯。"
        name = (name_map or {}).get(most_hammered, most_hammered)
        return (f"叮——「最想锤的人」出炉：{name}。锤是流量，接住是本事——"
                "请在终局陈词里自证清白。")

    def heart_quiz_show(self, correct: bool, teaching: str = "") -> str:
        """M2 心声窃听器结算演出（结算句为 D 组文案原样 + 教学点揭示）。"""
        settle = self.segments.heart_quiz_settle
        line = settle.get("win" if correct else "lose") or \
            ("叮——窃听成功。心声已解密，但请温柔使用。" if correct
             else "叮——这是口供（嘴硬版）。心声从来不加班。")
        return line + (f"\n教学点：{teaching}" if teaching and correct else "")

    def quick_quiz(self, stats: dict | None = None) -> dict | None:
        """快问快答：优先 segments_p2 §二 20 题题库（选项确定性乱序防泄答案位）；
        题库缺失时回落已发放线索自造题（v1 机制，同样确定性，不泄底）。"""
        bank = self.segments.quiz_bank
        if bank:
            self._quiz_seq += 1
            q = dict(bank[self._quiz_seq % len(bank)])
            options = list(q["options"])
            answer_text = q["answer_text"]
            if answer_text not in options:
                options[0] = answer_text
            rng = random.Random(f"{self._quiz_seq}|{q['question']}|{len(options)}")
            rng.shuffle(options)
            return {"question": q["question"], "options": options,
                    "answer_index": options.index(answer_text),
                    "answer_text": answer_text, "taunt": q["taunt"],
                    "source": "segments_bank"}
        return self._quiz_from_clues(stats)

    def _quiz_from_clues(self, stats: dict | None) -> dict | None:
        stats = stats or {}
        clues = [c for c in stats.get("clues_held", [])
                 if c.get("name") and (c.get("location") or c.get("tags"))]
        if not clues:
            return None
        self._quiz_seq += 1
        target = clues[self._quiz_seq % len(clues)]
        if self._quiz_seq % 2 == 1 and target.get("location"):
            pool = [loc for loc in sorted({c.get("location") for c in
                                           stats.get("clues_held", []) if c.get("location")})
                    if loc != target.get("location")]
            pool += [l for l in ("监控室", "茶水间", "天台", "档案室", "前台")
                     if l != target.get("location") and l not in pool]
            options = pool[:3] + [target["location"]]
            return self._pack_quiz(
                f"线索《{target['name']}》最初是在哪个地点被找到的？",
                options, target["location"],
                f"档案原文：{target.get('fact', '')[:60]}")
        truth_tag = (target.get("tags") or ["档案"])[0]
        wrong = []
        for c in clues:
            t = (c.get("tags") or [None])[0]
            if t and t != truth_tag and t not in wrong:
                wrong.append(t)
        wrong += ["鱼干库存表", "上周考勤", "食堂菜单"]
        options = wrong[:3] + [truth_tag]
        return self._pack_quiz(
            f"以下哪一项是线索《{target['name']}》的关键词标签？",
            options, truth_tag, f"档案原文：{target.get('fact', '')[:60]}")

    @staticmethod
    def _pack_quiz(question: str, options: list, answer, explain: str) -> dict:
        options = list(dict.fromkeys(options))[:4]
        if answer not in options:
            options[-1] = answer
        rng = random.Random(hash((question, str(options))) & 0xFFFF)
        shuffled = options[:]
        rng.shuffle(shuffled)
        return {"question": question, "options": shuffled,
                "answer_index": shuffled.index(answer),
                "answer_text": answer, "taunt": "", "explain": explain,
                "source": "clue_fallback"}

    # ================================================== P2 终局锐评（非 segments，保留）
    def final_verdict(self, ending: dict, npc_reports: list[dict]) -> str:
        """终局陈词锐评。阵营暗置铁律（CONTRACTS §四.4）：陈词在投票前，
        输入 npc_reports 若含 faction 一律防御性剥离，输出不得出现阵营信息。"""
        safe_reports = [{k: v for k, v in (r or {}).items() if k != "faction"}
                        for r in (npc_reports or [])]
        user = (f"演出位说明：终局陈词锐评。\n"
                f"ending_json：{json.dumps(ending, ensure_ascii=False)}\n"
                f"npc_reports_json：{json.dumps(safe_reports, ensure_ascii=False)}\n"
                f"硬规则：不出现任何阵营归属（污染/求真阵营等字样），只锐评行为。")
        return self._gen("final_verdict", "showtime_p2.md", user, "show_final_verdict")

    # ================================================== 防卡死备忘录（动态难度）
    def memo(self, level: int, hints: dict) -> dict:
        lv = min(3, max(1, level))
        user = (f"演出位说明：防卡死备忘录。\n"
                f"level：{lv}\n"
                f"locations：{json.dumps(hints.get('locations', []), ensure_ascii=False)}\n"
                f"loc_hint：{hints.get('loc_hint', '')}\n"
                f"kw_hint：{hints.get('kw_hint', '')}")
        text = self._gen(f"memo{lv}", "showtime_memo.md", user, f"show_memo{lv}")
        return {"level": lv, "memo_text": text, "hints": hints}

    # ------------------------------------------------------------ 辅助
    @staticmethod
    def _safe_stats(stats: dict) -> dict:
        slim = dict(stats)
        slim["clues_held"] = [{"name": c.get("name"), "location": c.get("location"),
                               "tier": c.get("tier") or c.get("level")}
                              for c in stats.get("clues_held", [])]
        slim["evidence_cards"] = [{"evidence_id": e.get("evidence_id"),
                                   "truth_nodes": e.get("truth_nodes")}
                                  for e in stats.get("evidence_cards", [])]
        for key in ("endings", "chat_keywords", "env_clues_seen"):   # set → list
            if key in slim:
                slim[key] = sorted(str(x) for x in (slim[key] or set()))
        if "counsel_multi" in slim:
            slim["counsel_multi"] = {k: sorted(v) for k, v in slim["counsel_multi"].items()}
        # 阵营暗置铁律（CONTRACTS §四.4）：演出层任何序列化输出不含 faction
        for c in slim.get("clues_held", []):
            c.pop("faction", None)
        for c in slim.get("npc_reports", []) or []:
            if isinstance(c, dict):
                c.pop("faction", None)
        return slim
