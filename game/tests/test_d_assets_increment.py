"""G 增量④：D 资产增量校验 —— 台词埋点（segments_p1.md）/ 成就库 / 鱼干支线 / party 内容位。

文案资产只做「结构完整性 + 硬规则合规」（禁语/防泄底/覆盖面），不改判任何创作内容。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import SCENARIO_DIR

pytestmark = pytest.mark.assets

BAN_WORDS = ("看山在局控室", "看山设局", "系统音是看山", "自导自演")


def _read(name: str) -> str:
    return (SCENARIO_DIR / "scripts" / name).read_text(encoding="utf-8")


def _ban_hit(text: str) -> str | None:
    """泄底词扫描：命中且所在行不是「禁语规则行」（规则行本身要列出禁词）才返回词。"""
    for ln in text.splitlines():
        is_rule = ("禁" in ln or "泄底" in ln) and any(w in ln for w in BAN_WORDS)
        if is_rule:
            continue
        for w in BAN_WORDS:
            if w in ln:
                return w
    return None


class TestSegmentsP1:
    """scripts/segments_p1.md —— P1 三环节台词埋点（D 组增量 #2 的 P1 部分）。"""

    @pytest.fixture(scope="class")
    def seg(self):
        return _read("segments_p1.md")

    def test_structure_three_sections(self, seg):
        assert "## 一、抽风池" in seg
        assert "## 二、心病急诊室" in seg
        assert "## 三、头条话题" in seg

    def test_glitch_pool_complete(self, seg):
        """抽风惩罚池 ≥8 条 + 故障播报池 ≥5 条 + 押注结算句 ≥3 条。"""
        s1 = seg.split("## 二、")[0]
        punish = [ln for ln in s1.splitlines() if "【惩罚：" in ln]
        assert len(punish) >= 8, f"抽风惩罚池仅 {len(punish)} 条"
        broadcast = [ln for ln in s1.splitlines() if "【叮——" in ln or "不出" in ln]
        assert len(broadcast) >= 5, f"故障播报池仅 {len(broadcast)} 条"
        assert s1.count("押") >= 4 and "开盘" in s1 and "结算（猜中）" in s1

    def test_er_covers_all_8_npcs(self, seg):
        """急诊室红灯状态词必须覆盖全部 8 个 NPC（按角色卡名核对）。"""
        chars = [json.loads(f.read_text(encoding="utf-8"))
                 for f in sorted((SCENARIO_DIR / "characters").glob("*.json"))]
        names = {c["name"] for c in chars}
        covered = {n for n in names if f"| {n} |" in seg}
        missing = names - covered
        assert not missing, f"红灯状态词缺角色：{missing}"

    def test_headline_pool_and_bid_words(self, seg):
        s3 = seg.split("## 三、")[1]
        topics = [ln for ln in s3.splitlines() if "《" in ln and "》" in ln]
        count = sum(ln.count("《") for ln in topics)
        assert count >= 8, f"头条话题池仅 {count} 条"
        assert "开标" in s3 and "竞标" in s3

    def test_broadcast_accident_whitelist_pool_no_case_info(self, seg):
        """白名单心声池：不得含案情词（与 engine 白名单词表一致）。"""
        from engine.memory_system import _BROADCAST_BLOCK_WORDS
        assert "白名单池" in seg
        pool_start = seg.index("白名单池")
        pool_text = seg[pool_start:pool_start + 400]
        for w in _BROADCAST_BLOCK_WORDS:
            for quote in pool_text.split("「")[1:]:
                body = quote.split("」")[0]
                assert w not in body, f"白名单心声含案情词 {w}：{body}"

    def test_no_ban_words_anywhere(self, seg):
        w = _ban_hit(seg)
        assert w is None, f"P1 台词埋点泄底：{w}"

    def test_fact_neutral_rule_written(self, seg):
        assert "不进证据链" in seg and "禁用" in seg


class TestAchievementsAsset:
    def test_file_and_json_block(self):
        text = _read("achievements.md")
        assert "```json" in text and "ach_zhenshan" in text
        assert "稀有度：铜 <15%" in text  # 稀有度口径说明

    def test_unlock_copy_hard_rule_written(self):
        text = _read("achievements.md")
        assert "成就不泄底" in text


class TestActScripts:
    """三幕剧本 + 诊室 + credits：P1/P2 环节埋点宿主文件存在且合规。"""

    @pytest.mark.parametrize("name", ["act1_chumen.md", "act2_xinsheng_xielu.md",
                                      "act3_hupi_demao.md", "counsel_clinic.md",
                                      "credits.md", "dm_system_voice.md"])
    def test_exists_nonempty_no_ban(self, name):
        text = _read(name)
        assert len(text) > 200, f"{name} 疑似空壳"
        w = _ban_hit(text)
        assert w is None, f"{name} 泄底词 {w}"

    def test_dm_voice_has_forbidden_section(self):
        text = _read("dm_system_voice.md")
        assert "禁语（硬规则）" in text


class TestFishSideQuest:
    """鱼干寻物支线（P3 彩蛋）：文案/位置定义已交付（collectibles_p3.md）。

    交付面：3 处收集品位置定义 + 看山 Bot 隐藏语音文案（IndexTTS 2.5 按句切片）。
    引擎/场景图集成（scene_map.collectible 字段）未落地 → 判定源 pending（如实双断言）。
    """

    def test_collectibles_doc_defines_three_points(self):
        doc = (SCENARIO_DIR / "scripts" / "collectibles_p3.md").read_text(encoding="utf-8")
        assert "鱼干收集品 ×3" in doc or "收集品" in doc
        # 表格定义 3 个收集点（行首为 | 的数据行，排除表头/分隔）
        rows = [ln for ln in doc.splitlines()
                if ln.strip().startswith("|") and "—" not in ln.split("|")[1]
                and "id" not in ln.split("|")[1]]
        assert len(rows) >= 3, f"收集点定义不足 3：{len(rows)}"
        assert "语音" in doc  # 隐藏语音文案承载

    def test_scene_map_integration_pending(self):
        """引擎/E 集成点：scene_map 尚无 collectible 字段（交付后此断言应反转）。"""
        scen = json.loads((SCENARIO_DIR / "scenario.json").read_text(encoding="utf-8"))
        collectibles = [v for v in scen.get("scene_map", {}).values()
                        if isinstance(v, dict) and v.get("collectible")]
        assert collectibles == []

    def test_fish_copy_seeds_exist(self):
        hits = 0
        for sub in ("clues", "characters", "hotfeed"):
            for f in (SCENARIO_DIR / sub).glob("*.json"):
                if "鱼干" in f.read_text(encoding="utf-8"):
                    hits += 1
        assert hits >= 5


class TestPartyContentReadiness:
    """party 内容侧就绪位（mode=party 的 D/E 前提）。"""

    def test_scenario_player_count_supports_party(self):
        scen = json.loads((SCENARIO_DIR / "scenario.json").read_text(encoding="utf-8"))
        assert scen["player_count_min"] == 1 and scen["player_count_max"] >= 5

    def test_modes_declared(self):
        scen = json.loads((SCENARIO_DIR / "scenario.json").read_text(encoding="utf-8"))
        assert set(scen["modes"]) >= {"main", "daily", "quick"}
        # mode=party 服务端未放行（PENDING-F01）——契约增量同步前不要求 modes 声明 party
