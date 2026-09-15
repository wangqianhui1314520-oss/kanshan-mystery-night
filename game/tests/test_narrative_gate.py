"""叙事级闸门测试：V1 时间线一致性 / V2 真相可达性 / V3 伪证回路与凶手隐瞒。

纯结构测试：零网络、无 LLM 依赖（fixture 先 delenv 全部 AI 凭证）。
- 坏样本×3（手工迷你包）分别踩中 V1/V2/V3，断言 validate_dir 拦截；
- 好样本断言通过；
- kanshan 实测（tmp 副本）：三个新检查器 0 error（误伤豁免基准）；
- mutation test：NARRATIVE_GATE=0 关闭闸门 → 坏样本从「被拦」变「漏过」。

运行：cd game && python -m pytest tests/test_narrative_gate.py -v --basetemp=data/_pytest_tmp
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.validate import validate_dir

KANSHAN = Path(__file__).resolve().parent.parent / "content" / "scenarios" / "kanshan"


@pytest.fixture(autouse=True)
def _no_ai_env(monkeypatch):
    """零网络铁律：清空全部 AI 凭证。"""
    for key in ("ZHIHU_APP_KEY", "ZHIHU_ZHIDA_URL", "ZHIHU_ACCESS_SECRET",
                "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)


def _copy_tree_safe(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.iterdir():
        target = dest / path.name
        if path.is_dir():
            _copy_tree_safe(path, target)
        else:
            target.write_bytes(path.read_bytes())


# ---------------------------------------------------------------------------
# 迷你剧本包工厂（最小合法 schema：scenario/truth/timeline + characters×2 +
# clues×4）。demo 配额较大，QUOTA 不达标会先报错——断言只看 NARR- 前缀，
# 与本次改动无关的既有结构错误不纳入。
# ---------------------------------------------------------------------------

def _mini_pack(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "characters").mkdir(parents=True)
    (root / "clues").mkdir()
    (root / "scripts").mkdir()
    (root / "scenario.json").write_text(json.dumps({
        "id": name,
        "acts": [
            {"id": "act1", "name": "一", "stage": "break_ice", "actions_allocated": 3},
            {"id": "act2", "name": "二", "stage": "investigate", "actions_allocated": 3},
        ],
        "scene_map": {
            "loc_reception": {"name": "前台", "type": "base", "clue_pool": ["clue_001"]},
            "loc_archive": {"name": "档案室", "type": "crime_scene", "clue_pool": ["clue_002"]},
        },
    }, ensure_ascii=False), encoding="utf-8")
    (root / "truth.json").write_text(json.dumps({
        "culprit": {"character": "char_01", "name": "甲"},
        "truth_nodes": [
            {"id": "tn_01", "name": "真相一", "proof_clues": ["clue_001", "clue_002"]},
            {"id": "tn_02", "name": "真相二", "proof_clues": ["clue_003"]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (root / "timeline.json").write_text(json.dumps({
        "timeline": [
            {"time": "20:00", "character": "char_01", "location": "前台", "action": "到场"},
            {"time": "21:00", "character": "char_02", "location": "档案室", "action": "翻档案"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    for cid, faction in (("char_01", "pollution"), ("char_02", "public")):
        (root / "characters" / f"{cid}.json").write_text(json.dumps(
            {"id": cid, "faction": faction}, ensure_ascii=False), encoding="utf-8")
    # 4 条线索：clue_001/002 证明 tn_01；clue_003 证明 tn_02；clue_004 为 fake
    clue_tns = {"clue_001": ["tn_01"], "clue_002": ["tn_01"],
                "clue_003": ["tn_02"], "clue_004": []}
    for cid, tns in clue_tns.items():
        body = {"id": cid, "tier": "fake" if cid == "clue_004" else "public",
                "location": "前台", "linked_truth_nodes": tns}
        if cid == "clue_004":
            body["fake_of"] = "clue_001"
        (root / "clues" / f"{cid}.json").write_text(json.dumps(
            body, ensure_ascii=False), encoding="utf-8")
    (root / "scripts" / "player_book_char_01.json").write_text(json.dumps({
        "char_id": "char_01", "you_are": "你是甲", "goals": ["隐瞒真相"],
        "secrets": ["我是凶手"],
    }, ensure_ascii=False), encoding="utf-8")
    return root


def _run_checks(root: Path) -> tuple[list, list]:
    """经 validate_dir 跑闸门，按 NARR- 前缀过滤出三个叙事检查器的输出。
    （走 validate_dir 而非直调函数：mutation test 注释掉调用时测试才会失败）"""
    result = validate_dir(root)
    errors = [e for e in result["errors"] if e.startswith("NARR-")]
    warnings = [w for w in result["warnings"] if w.startswith("NARR-")]
    return errors, warnings


# ------------------------------- 好样本 ------------------------------------

def test_good_mini_pack_passes(tmp_path):
    root = _mini_pack(tmp_path, "good_pack")
    errors, _ = _run_checks(root)
    assert not errors, errors


# ------------------------------- V1 坏样本 ---------------------------------

def test_v1_overlapping_events_blocked(tmp_path):
    root = _mini_pack(tmp_path, "v1_overlap")
    tl = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    tl["timeline"].append(
        {"time": "21:00", "character": "char_02", "location": "前台",
         "action": "同时在别处出现"})
    (root / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
    errors, _ = _run_checks(root)
    assert any(e.startswith("NARR-V1:") for e in errors), errors


# ------------------------------- V2 坏样本 ---------------------------------

def test_v2_truth_reaches_nonexistent_scene_blocked(tmp_path):
    root = _mini_pack(tmp_path, "v2_unreachable")
    c3 = json.loads((root / "clues" / "clue_003.json").read_text(encoding="utf-8"))
    c3["location"] = "不存在的密室"  # tn_02 唯一证明被挪出全部场景
    (root / "clues" / "clue_003.json").write_text(json.dumps(c3, ensure_ascii=False), encoding="utf-8")
    errors, _ = _run_checks(root)
    assert any("NARR-V2:" in e and "不可达" in e for e in errors), errors


def test_v2_zero_proof_blocked(tmp_path):
    root = _mini_pack(tmp_path, "v2_zero_proof")
    truth = json.loads((root / "truth.json").read_text(encoding="utf-8"))
    truth["truth_nodes"].append({"id": "tn_03", "name": "孤证真相", "proof_clues": []})
    (root / "truth.json").write_text(json.dumps(truth, ensure_ascii=False), encoding="utf-8")
    errors, _ = _run_checks(root)
    assert any("NARR-V2:" in e and "零证明" in e for e in errors), errors


# ------------------------------- V3 坏样本 ---------------------------------

def test_v3_unbreakable_fake_blocked(tmp_path):
    root = _mini_pack(tmp_path, "v3_fake_loop")
    c4 = json.loads((root / "clues" / "clue_004.json").read_text(encoding="utf-8"))
    c4["fake_of"] = None  # 伪证失去原件，也无共享真相节点 → 不可戳破
    (root / "clues" / "clue_004.json").write_text(json.dumps(c4, ensure_ascii=False), encoding="utf-8")
    errors, _ = _run_checks(root)
    assert any("NARR-V3:" in e and "伪证" in e for e in errors), errors


def test_v3_culprit_without_secrets_blocked(tmp_path):
    root = _mini_pack(tmp_path, "v3_no_secret")
    book_path = root / "scripts" / "player_book_char_01.json"
    book = json.loads(book_path.read_text(encoding="utf-8"))
    book["secrets"] = []  # 凶手无隐瞒
    book_path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    errors, _ = _run_checks(root)
    assert any("NARR-V3:" in e and "无隐瞒" in e for e in errors), errors


# ------------------------------- kanshan 实测 ------------------------------

def test_kanshan_narrative_gate_no_errors(tmp_path):
    """kanshan 权威主剧本（tmp 副本绕开 BLACKLIST 现有契约）：
    三个叙事检查器必须 0 error——误伤豁免的回归锚点。
    注：validate_dir(真实 kanshan 目录) 因 BLACKLIST 现有契约恒 ok=False
    （见 tests/test_studio.py::test_kanshan_blacklisted），故以副本验证数据。"""
    tmp_root = tmp_path / "kanshan_audit"
    _copy_tree_safe(KANSHAN, tmp_root)
    errors, warnings = _run_checks(tmp_root)
    assert not errors, errors
    # 两处设计内豁免（error 已降级 warning）
    assert any("tn_08" in w for w in warnings), warnings
    assert any("secrets" in w for w in warnings), warnings


# ------------------------------- mutation test -----------------------------

def test_evidence_gate_rejects_missing_third_link(tmp_path):
    from studio import generate, scenario_dir
    job = generate("证据门禁 mutation：缺第三条 link", use_llm=False)
    src = scenario_dir(job["id"])
    dest = tmp_path / job["id"]
    _copy_tree_safe(src, dest)
    truth = json.loads((dest / "truth.json").read_text(encoding="utf-8"))
    node = truth["truth_nodes"][0]
    links = [
        path for path in (dest / "clues").glob("clue_*.json")
        if node["id"] in (json.loads(path.read_text(encoding="utf-8")).get("linked_truth_nodes") or [])
    ]
    assert len(links) >= 3
    clue = json.loads(links[0].read_text(encoding="utf-8"))
    clue["linked_truth_nodes"] = [tid for tid in clue["linked_truth_nodes"] if tid != node["id"]]
    links[0].write_text(json.dumps(clue, ensure_ascii=False), encoding="utf-8")
    gate = validate_dir(dest)
    assert not gate["ok"]
    assert any(e.startswith("NARR-EVIDENCE:") and node["id"] in e for e in gate["errors"])


def test_evidence_gate_excludes_fake_and_dangling_links(tmp_path):
    from studio import generate, scenario_dir
    job = generate("证据门禁 mutation：fake 与悬空 link", use_llm=False)
    src = scenario_dir(job["id"])
    dest = tmp_path / job["id"]
    _copy_tree_safe(src, dest)
    fake_path = dest / "clues" / "clue_012.json"
    fake = json.loads(fake_path.read_text(encoding="utf-8"))
    fake["linked_truth_nodes"] = ["tn_01", "tn_99"]
    fake_path.write_text(json.dumps(fake, ensure_ascii=False), encoding="utf-8")
    real_path = dest / "clues" / "clue_001.json"
    real = json.loads(real_path.read_text(encoding="utf-8"))
    real["linked_truth_nodes"] = [tid for tid in real["linked_truth_nodes"] if tid != "tn_01"]
    real_path.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
    gate = validate_dir(dest)
    assert not gate["ok"]
    # The fake link does not make tn_01 composeable; the dangling id is also
    # rejected by the ordinary reference gate.
    assert any("clue_012 指向不存在节点 tn_99" in e for e in gate["errors"])
    assert any(e.startswith("NARR-EVIDENCE:") and "tn_01" in e for e in gate["errors"])


def test_mutation_gate_off_lets_bad_pack_through(tmp_path, monkeypatch):
    """QA 铁律：NARRATIVE_GATE=0 关闭闸门（等价于注释掉三检查器调用），
    V1 坏样本从「被拦」变「漏过」。报告留存两次运行输出：
    - 默认（开闸）：test_v1_overlapping_events_blocked 拦截 ✓
    - NARRATIVE_GATE=0（关闸）：0 error 漏过 ✓
    """
    root = _mini_pack(tmp_path, "mutation_v1")
    tl = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    tl["timeline"].append(
        {"time": "21:00", "character": "char_02", "location": "前台",
         "action": "同时在别处出现"})
    (root / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NARRATIVE_GATE", "0")
    # 整包 validate 走 env 开关路径：坏样本漏过（仅剩与 NARR 无关的既有错误）
    result = validate_dir(root)
    assert not any(e.startswith("NARR-") for e in result["errors"]), result["errors"]
