"""G 原矩阵②：schema 校验 —— D 产出全部 JSON 对照 schemas/*.example.json。

校验策略：示例 JSON 视为「字段结构基线」（契约约定只增不改）——
每个内容文件必须包含示例的全部顶层键且类型一致；额外键允许（D STATUS §四合规自查）。
附跨文件引用完整性校验（线索池/真相节点/记忆归属/辟谣对位/时间线角色）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.schema


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _example(game_root: Path, name: str) -> dict:
    return _load(game_root / "schemas" / f"{name}.example.json")


def _check_keys(cls_name: str, data: dict, example: dict):
    """示例顶层键全部存在且 JSON 类型一致。"""
    missing = [k for k in example if k not in data]
    assert not missing, f"{cls_name} 缺少契约键 {missing}"
    for k, v in example.items():
        if k in data and data[k] is not None and v is not None:
            assert isinstance(data[k], type(v)), (
                f"{cls_name}.{k} 类型不符：期望 {type(v).__name__}，"
                f"实际 {type(data[k]).__name__}")


class TestSchemaConformance:
    def test_clues(self, game_root, scenario_dir):
        example = _example(game_root, "clue")
        files = sorted((scenario_dir / "clues").glob("*.json"))
        assert len(files) == 34
        for f in files:
            _check_keys(f.name, _load(f), example)

    def test_characters(self, game_root, scenario_dir):
        example = _example(game_root, "character")
        files = sorted((scenario_dir / "characters").glob("*.json"))
        assert len(files) == 8
        for f in files:
            data = _load(f)
            _check_keys(f.name, data, example)
            assert data["faction"] in ("truth", "pollution", "swayable")

    def test_memory_versions(self, game_root, scenario_dir):
        example = _example(game_root, "memory_version")
        files = sorted((scenario_dir / "memory").glob("*.json"))
        assert len(files) == 24, f"记忆文件应 24 份（8 角色 × V1-V3），实际 {len(files)}"
        for f in files:
            data = _load(f)
            _check_keys(f.name, data, example)
            assert data["version"] in (1, 2, 3)
            for b in data["blocks"]:
                assert b["layer"] in ("said", "heart"), f"{f.name} layer 非法"
                assert b["integrity"] in ("original", "edited", "deleted")

    def test_hot_posts(self, game_root, scenario_dir):
        example = _example(game_root, "hot_post")
        files = sorted((scenario_dir / "hotfeed").glob("*.json"))
        assert len(files) == 44
        for f in files:
            data = _load(f)
            _check_keys(f.name, data, example)
            assert isinstance(data["is_fake"], bool)
            assert 0 <= int(data["heat_delta"]) <= 20
            assert 1 <= int(data["round"]) <= 9

    def test_knowledge_cards(self, game_root, scenario_dir):
        example = _example(game_root, "knowledge_card")
        files = sorted((scenario_dir / "knowledge_cards").glob("*.json"))
        assert len(files) == 10
        for f in files:
            data = _load(f)
            _check_keys(f.name, data, example)
            assert data["effect"] in ("memory_unlock", "evidence", "buff_ap",
                                      "plot_fragment", "boss_key"), f.name
            assert data["golden_lines"], f"{f.name} 金句为空（署名硬规则载体）"
            assert data["author"], f"{f.name} 作者署名缺失"

    def test_timeline_shape(self, scenario_dir):
        data = _load(scenario_dir / "timeline.json")
        assert "timeline" in data
        for e in data["timeline"]:
            assert {"character", "time", "location"} <= set(e)
        assert "tamper_point_index" in data  # D 契约件：篡改点索引

    def test_truth_shape(self, scenario_dir):
        data = _load(scenario_dir / "truth.json")
        assert "culprit" in data and "truth_nodes" in data
        assert len(data["truth_nodes"]) == 14
        assert data.get("boss_layer"), "里层 boss_layer 缺失（DM_BOSS_DESIGN 契约）"


class TestCrossFileIntegrity:
    """跨文件引用：D STATUS §二 自检项的独立复跑（G 不信任生成器自检）。"""

    @pytest.fixture(scope="class")
    def index(self, scenario_dir):
        clues = {c["id"]: c for f in (scenario_dir / "clues").glob("*.json")
                 for c in [_load(f)]}
        truth = _load(scenario_dir / "truth.json")
        chars = {c["id"]: c for f in (scenario_dir / "characters").glob("*.json")
                 for c in [_load(f)]}
        posts = {p["id"]: p for f in (scenario_dir / "hotfeed").glob("*.json")
                 for p in [_load(f)]}
        cards = {k["id"]: k for f in (scenario_dir / "knowledge_cards").glob("*.json")
                 for k in [_load(f)]}
        tl = _load(scenario_dir / "timeline.json")["timeline"]
        scene = _load(scenario_dir / "scenario.json")["scene_map"]
        return dict(clues=clues, truth=truth, chars=chars, posts=posts,
                    cards=cards, tl=tl, scene=scene)

    def test_truth_proof_clues_exist(self, index):
        for n in index["truth"]["truth_nodes"]:
            for cid in n.get("proof_clues", []):
                assert cid in index["clues"], f"{n['id']} 引用不存在的线索 {cid}"

    def test_fake_of_targets_exist(self, index):
        for cid, c in index["clues"].items():
            if c.get("fake_of"):
                assert c["fake_of"] in index["clues"], f"{cid}.fake_of 无效"
                assert index["clues"][c["fake_of"]].get("tier") != "fake"

    def test_scene_pools_reference_existing_clues(self, index):
        for loc, meta in index["scene"].items():
            for cid in meta.get("clue_pool", []):
                assert cid in index["clues"], f"场景 {loc} clue_pool 含未知线索 {cid}"
                assert index["clues"][cid].get("location") == meta.get("name"), (
                    f"{loc} 池中 {cid} 的 location 与场景名不符")

    def test_post_clue_refs_valid(self, index):
        for pid, p in index["posts"].items():
            if p.get("clue_ref"):
                assert p["clue_ref"] in index["clues"], f"{pid}.clue_ref 无效"

    def test_kc_binds_target_existing_chars(self, index):
        for kid, k in index["cards"].items():
            b = k.get("binds")
            if b and not b.startswith(("team", "archive")):
                assert b in index["chars"], f"{kid}.binds 指向不存在角色 {b}"

    def test_memory_owner_matches_chars(self, index, scenario_dir):
        owners = {_load(f)["owner"] for f in (scenario_dir / "memory").glob("*.json")}
        assert owners == set(index["chars"]), "记忆归属与角色卡不一致"

    def test_timeline_characters_valid(self, index, scenario_dir):
        """时间线角色 = 角色卡 ∪ system_npcs（archiv3/dm 演出型 NPC）∪ kanshan（DM 本人）。"""
        scen = _load(scenario_dir / "scenario.json")
        sys_ids = {n["id"] for n in scen.get("system_npcs", [])}
        valid = set(index["chars"]) | sys_ids | {"kanshan", "dm"}
        for e in index["tl"]:
            assert e["character"] in valid, (
                f"时间线未知角色 {e['character']}（既非角色卡也非 system_npcs）")

    def test_tier_distribution_contract(self, index):
        tiers: dict[str, int] = {}
        for c in index["clues"].values():
            t = c.get("tier") or c.get("level") or "public"
            tiers[t] = tiers.get(t, 0) + 1
        assert tiers == {"public": 7, "limited": 11, "hidden": 5,
                         "fake": 6, "boss_flaw": 5}

    def test_flaw_chain_complete(self, index):
        flaws = {c.get("flaw_id") for c in index["clues"].values()
                 if c.get("tier") == "boss_flaw"}
        assert flaws == {f"flavor_{i}" for i in range(1, 6)}

    def test_refute_target_design(self, index):
        """对位帖 14（10 水军 + 4 真帖）；真帖必须带 clue_ref，辟谣可解锁真线索。"""
        card_tags = {k.get("topic_tag") for k in index["cards"].values()}
        matched = [p for p in index["posts"].values()
                   if p.get("topic_tag") in card_tags]
        assert len(matched) == 14, f"对位帖应 14（10 水军+4 真帖），实际 {len(matched)}"
        real = [p for p in matched if not p.get("is_fake")]
        fake = [p for p in matched if p.get("is_fake")]
        assert len(real) == 4 and len(fake) == 10
        for p in real:
            assert p.get("clue_ref") in index["clues"], (
                f"{p['id']} 真帖缺少有效 clue_ref")

    def test_condition_grammar_documented_matches_used(self, scenario_dir, index):
        """scenario.condition_grammar 声明的语法族 = 实际用到的条件族。"""
        doc = _load(scenario_dir / "scenario.json")["condition_grammar"]
        families = {"默认", "evidence", "memory", "counsel", "boss", "chat", "review",
                    "echo", "debate"}
        for fam in ("evidence", "memory", "counsel", "chat", "review"):
            assert f"{fam}:" in doc, f"condition_grammar 未声明 {fam}: 语法"
        used = {str(c.get("unlock_condition", "默认")).split(":")[0]
                for c in index["clues"].values()}
        assert used <= families, f"出现未声明语法族：{used - families}"
