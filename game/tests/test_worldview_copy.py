"""玩家可见文案必须贴合 kanshan 权威层：盘点夜、监控时段、阵营、物理。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KAN = ROOT / "content" / "scenarios" / "kanshan"
FRONT = ROOT / "frontend" / "js"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_scenario_summary_uses_camera_window_not_seven_minutes():
    sc = _load(KAN / "scenario.json")
    assert "21:07–21:15" in sc["summary"] or "21:07-21:15" in sc["summary"]
    assert "7 分钟空洞" not in sc["summary"]
    assert "跳过破冰" in sc["modes"]["quick"]


def test_timeline_lock_then_start():
    tl = _load(KAN / "timeline.json")
    assert "21:00" in tl["case_time"] and "23:00" in tl["case_time"]
    times = [row["time"] for row in tl["timeline"]]
    assert times.index("21:45") < times.index("21:47")


def test_factions_match_authority():
    expect = {
        "char_01": "pollution",
        "char_02": "truth",
        "char_03": "swayable",
        "char_04": "swayable",
        "char_05": "truth",
        "char_06": "truth",
        "char_07": "truth",
        "char_08": "truth",
    }
    for cid, fac in expect.items():
        assert _load(KAN / "characters" / f"{cid}.json")["faction"] == fac
        assert _load(KAN / "booklets" / f"{cid}.json")["faction"] == fac


def test_booklets_no_anniversary_and_physics_split():
    blob = "".join(p.read_text(encoding="utf-8") for p in (KAN / "booklets").glob("*.json"))
    assert "周年庆" not in blob
    pub = _load(KAN / "booklets" / "public.json")
    tonight = pub["covers"]["A"]["tonight"]
    assert "监控" in tonight and "存证" in tonight
    inv = _load(KAN / "booklets" / "investigator.json")
    assert "特许" in inv["covers"]["A"]["tonight"]
    assert "芯片删了" not in inv["covers"]["A"]["tonight"]
    ch6 = _load(KAN / "booklets" / "char_06.json")
    assert "二十一点二十八分" in ch6["covers"]["A"]["tonight"]


def test_frontend_copy_aligned():
    main = (FRONT / "main.js").read_text(encoding="utf-8")
    ux = (FRONT / "ux.js").read_text(encoding="utf-8")
    data = (FRONT / "data.js").read_text(encoding="utf-8")
    books = (FRONT / "booklets.js").read_text(encoding="utf-8")
    assert "周年庆" not in main and "周年庆" not in ux and "周年庆" not in books
    assert "周五盘点夜" in main
    assert "22:00-23:00" not in data
    assert "20:00 加班到岗" in data
    assert "faction: 'pollution'" not in data
    assert "faction: 'swayable'" not in data
    assert "faction: 'truth'" not in data
    assert "#监控出现21:07-21:15空洞#" in (KAN / "hotfeed" / "post_009.json").read_text(encoding="utf-8")
