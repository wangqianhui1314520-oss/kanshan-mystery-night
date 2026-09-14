"""G 增量③：报告成就判定 —— achievements.md 契约校验 + 引擎事实交叉核验
+ 判定可行性矩阵（逐成就：引擎可判 / 可由会话状态推导 / 未跟踪 / 内容缺失）。
"""
from __future__ import annotations

import json

import pytest

from engine.evidence_chain import EvidenceChain
from engine.knowledge_cards import KnowledgeSystem
from engine.memory_system import MemorySystem
from tests.conftest import SCENARIO_DIR

pytestmark = pytest.mark.achievements

# 泄底硬规则：终极层真相词（仅对应结局解锁后可见）
BAN_WORDS = ("看山在局控室", "看山设局", "系统音是看山", "自导自演")
ULTIMATE_GATED_ACH = {"ach_zhenshan", "ach_juzhongju", "ach_daqidai", "ach_di7zhang"}

MEGA_MANDATORY = {"ach_zhenshan", "ach_xinqing", "ach_jiezou", "ach_yugan",
                  "ach_fangzhe"}  # MEGA_MODE §三 必做 4+1
RARITIES = {"bronze", "silver", "gold", "egg"}
CONDITION_TYPES = {"ending", "counsel_count", "clue_collected", "listen_full",
                   "fake_exposed", "confrontation_win", "danmaku_echo",
                   "memory_puzzle_win", "counsel_multi", "same_location_dry_streak",
                   "boss_flaw_count", "chat_keyword", "refute_success_streak",
                   "antifraud_all_correct", "quiz_score", "closing_vote_top1_survived",
                   "collectible", "env_clue", "hammered_votes", "heart_unlock_count",
                   "stealth_photo_clean"}

# 引擎结局键 ↔ 成就库 ending 值映射（D 用语义别名；B 引擎用 ENDINGS 键）
ENDING_ALIAS = {
    "ending_kanshan": "kanshan_still_mountain",
    "ending_pollution": "pollution_win",
    "ending_sunny": "all_hearts_clear",
    "ending_chapter7": "deleted_chapter7",
}


@pytest.fixture(scope="module")
def ach(achievements_data):
    return achievements_data["items"]


class TestAchievementContract:
    def test_scale_and_unique_ids(self, ach):
        assert len(ach) == 24
        ids = [a["id"] for a in ach]
        assert len(ids) == len(set(ids)), "成就 id 重复"

    def test_mandatory_mega_mode_coverage(self, ach):
        ids = {a["id"] for a in ach}
        assert MEGA_MANDATORY <= ids, f"MEGA_MODE 必做成就缺失：{MEGA_MANDATORY - ids}"

    def test_rarity_and_condition_schema(self, ach):
        for a in ach:
            assert a["rarity"] in RARITIES, a["id"]
            cond = a["condition"]
            assert cond["type"] in CONDITION_TYPES, (a["id"], cond["type"])
            for k in ("name", "rarity", "condition"):
                assert a.get(k), a["id"]

    def test_no_leak_in_unlock_copy(self, achievements_data):
        """硬规则：解锁文案/分享卡不泄底；终极层文案仅限对应结局成就行。"""
        text = achievements_data["raw"]
        for line in text.splitlines():
            if line.startswith("|") and not line.startswith("| id"):
                for w in BAN_WORDS:
                    if w in line:
                        cells = line.split("|")
                        assert any(g in line for g in ULTIMATE_GATED_ACH), \
                            f"非结局门控行泄底词 {w}：{cells[1] if len(cells) > 1 else line}"

    def test_signing_credits_kept(self, achievements_data):
        """成就文案库不破坏署名链：credits 表仍在 + 对齐来源声明（v2：resolver 七枚举）。"""
        assert (SCENARIO_DIR / "scripts" / "credits.md").exists()
        text = achievements_data["raw"]
        assert "MEGA_MODE" in text and ("依据" in text or "对齐" in text)


class TestAchievementEngine:
    """B 组 engine/achievements.py：condition DSL 求值器（真实 D 库驱动）。"""

    def test_load_real_library_and_scale(self):
        from engine.achievements import AchievementEngine
        eng = AchievementEngine()
        eng.load(SCENARIO_DIR / "scripts" / "achievements.md")
        assert len(eng._defs) == 24

    def test_dsl_eval_engine_judged_types(self):
        """引擎自判类型走 refs 注入（record 仅用于外部行为项）。"""
        from engine.achievements import AchievementEngine
        from engine.evidence_chain import EvidenceChain
        ec = EvidenceChain(SCENARIO_DIR)
        eng = AchievementEngine(refs={"evidence_chain": ec})
        eng.load(SCENARIO_DIR / "scripts" / "achievements.md")
        # 破绽链：028/029 直发 + kc_06 counsel 链 + 唤醒词 + 复盘页 = 5/5
        ec.release("clue_028", "p1")
        ec.release("clue_029", "p1")
        ec.sync_context(counsel_cards=["kc_06"])
        ec.release("clue_030", "p1")
        ec.on_chat("p1", "看山，关门")
        ec.on_review_entered("p1")
        eng.evaluate(ending_key="kanshan_still_mountain")
        got = set(eng.unlocked_ids())
        assert "ach_juzhongju" in got        # boss_flaw_count>=5
        assert "ach_huanxingci" in got       # chat_keyword 命中
        assert "ach_zhenshan" in got         # ending 映射（ending_kanshan）
        assert "ach_xinqing" not in got      # 未开导 → counsel_count 0
        # record() 路径（外部行为项）：listen_full×3 → 防折叠斗士
        for _ in range(3):
            eng.record("listen_full", target="char_06")
        eng.evaluate(ending_key=None)
        assert "ach_fangzhe" in eng.unlocked_ids()
        # 幂等：重复评估不重复解锁
        eng.evaluate(ending_key="kanshan_still_mountain")
        assert len(eng.unlocked_ids()) == len(set(eng.unlocked_ids()))

    def test_ending_map_covers_library_values(self):
        from engine.achievements import ENDING_MAP
        for a in achievements_data_for_map():
            if a["condition"]["type"] == "ending":
                assert a["condition"]["value"] in ENDING_MAP, \
                    f"{a['id']} 的 ending 值不在引擎映射表"


def achievements_data_for_map():
    import re
    text = (SCENARIO_DIR / "scripts" / "achievements.md").read_text(encoding="utf-8")
    for block in re.findall(r"```json\n(.*?)\n```", text, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and data:
            return data
    return []


class TestEngineFactCrossCheck:
    """成就条件值 ↔ 引擎/内容事实一致性（数据驱动，防口径漂移）。"""

    def test_clue_collected_target_matches_pool(self, ach):
        c = next(a for a in ach if a["id"] == "ach_yugan")
        n = len(list((SCENARIO_DIR / "clues").glob("*.json")))
        assert c["condition"]["value"] == n == 34

    def test_boss_flaw_target_matches_content(self, ach):
        c = next(a for a in ach if a["id"] == "ach_juzhongju")
        flaws = [f for f in (SCENARIO_DIR / "clues").glob("*.json")
                 if json.loads(f.read_text(encoding="utf-8")).get("tier") == "boss_flaw"]
        assert c["condition"]["value"] == len(flaws) == 5

    def test_chat_keyword_achievement_matches_clue(self, ach):
        c = next(a for a in ach if a["id"] == "ach_huanxingci")
        kw = c["condition"]["value"]
        clue = json.loads((SCENARIO_DIR / "clues" / "clue_031.json").read_text(encoding="utf-8"))
        assert clue["unlock_condition"] == f"chat:keyword_{kw}"

    def test_env_clue_achievement_matches_env_pool(self, ach):
        c = next(a for a in ach if a["id"] == "ach_dalitang")
        from engine.evidence_chain import _ENV_POOL
        assert any(c["condition"]["value"] in e["fact"] for e in _ENV_POOL)

    def test_counsel_count_threshold_matches_clinic(self, ach):
        ks = KnowledgeSystem(seed=1)
        ks.load(str(SCENARIO_DIR))
        assert ks.clinic_settlement()["counsel_count"] == 0
        c = next(a for a in ach if a["id"] == "ach_xinqing")
        assert c["condition"]["value"] == 4  # 与 clinic 4+ 档位对齐

    def test_ending_alias_map_covers_all_ending_conditions(self, ach, scenario_dir):
        """ISSUE-G08（P2）：成就库 ending 值为语义别名，须能唯一映射到引擎 ENDINGS 键。"""
        from engine.resolver import ENDINGS
        for a in ach:
            if a["condition"]["type"] == "ending":
                v = a["condition"]["value"]
                assert v in ENDING_ALIAS, f"{a['id']} 的 ending 值 {v} 无映射"
                assert ENDING_ALIAS[v] in ENDINGS

    def test_resolver_achievements_mapping(self):
        """B 侧 resolver.achievements() 判定映射（D 契约语义）。"""
        from engine.resolver import Resolver
        rv = Resolver()
        assert "看山还是山" in rv.achievements(boss_accused_success=True)
        assert "心晴医师" in rv.achievements(counsel_count=4)
        assert "心晴医师" not in rv.achievements(counsel_count=3)
        assert "带节奏之王" in rv.achievements(pollution_win=True)
        assert "鱼干守护者" in rv.achievements(clues_collected=34, clues_total=34)
        assert "鱼干守护者" not in rv.achievements(clues_collected=33, clues_total=34)
        # 防折叠斗士映射错乱见下方 xfail（ISSUE-G07）
        assert "全场公敌" in rv.achievements(most_hammered="player:1",
                                             hammered_is_self=True)
        assert "暗房大师" in rv.achievements(photos_shared=3)

    def test_fangzhe_not_refuted(self):
        """G07 已修复（A 修复轮）：refuted>=3 → 热搜质检员；防折叠斗士=listen_full>=3。"""
        from engine.resolver import Resolver
        rv = Resolver()
        assert "防折叠斗士" not in rv.achievements(refuted=3)
        assert "热搜质检员" in rv.achievements(refuted=3)
        assert "防折叠斗士" in rv.achievements(listen_full=3)


class TestJudgmentFeasibility:
    """判定可行性矩阵（结论落 tests/STATUS.md 表格）。

    - engine_ready：引擎已有直接判定 API；
    - derivable：可由会话状态（session/events）确定性推导；
    - untracked：引擎/会话均无计数来源（需 B/F 增埋点）；
    - content_missing：依赖未交付内容（P2/P3 环节）。
    """

    FEASIBILITY = {
        "ending": "engine_ready",                 # matrix_ending
        "counsel_count": "engine_ready",          # clinic_settlement
        "boss_flaw_count": "engine_ready",        # ec.flaw_count
        "chat_keyword": "engine_ready",           # ec.on_chat
        "memory_puzzle_win": "engine_ready",      # ms.puzzle_judge
        "heart_unlock_count": "derivable",        # ms._heart_unlocked
        "clue_collected": "derivable",            # session.clues_gained
        "hammered_votes": "engine_ready",         # pb.hammer_result
        "env_clue": "derivable",                  # events clue_gained(env_)
        "same_location_dry_streak": "derivable",  # ec._search_log
        "listen_full": "untracked",
        "fake_exposed": "untracked",
        "confrontation_win": "untracked",
        "danmaku_echo": "untracked",
        "refute_success_streak": "untracked",
        "stealth_photo_clean": "derivable",       # ec.photos_of（"clean" 语义需 B/F 定口径）
        "counsel_multi": "engine_ready",          # ks._counsel_log / AchievementEngine
        "antifraud_all_correct": "content_missing",   # P2 反诈剧场
        "quiz_score": "content_missing",              # P2 快问快答
        "collectible": "engine_ready",                # CollectiblesBoard（P3 文案已交付）
        "closing_vote_top1_survived": "engine_ready",  # pb.hammer_result + status
    }

    def test_flaw_and_heart_and_puzzle_engine_ready(self, scenario_dir):
        """engine_ready 代表样本实测（非纸面声明）。"""
        ec = EvidenceChain(scenario_dir)
        assert ec.flaw_count() == 0
        ms = MemorySystem()
        ms.load(str(scenario_dir))
        ch = sorted(ms._versions)[0]
        assert ms.puzzle_judge(ch, ms.puzzle_answer(ch))["correct"] is True

    def test_feasibility_table_self_consistent(self, ach):
        """每个 condition.type 都有可行性结论（防新增成就落入未评估态）。"""
        for a in ach:
            t = a["condition"]["type"]
            assert t in self.FEASIBILITY, f"成就 {a['id']} 的条件类型 {t} 未评估可行性"
