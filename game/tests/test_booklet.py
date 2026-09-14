"""分幕闭卷：可见性、禁语、启发式按本行动、AI actor 门控。"""
from __future__ import annotations

from engine.booklet import BookletLibrary, chapter_to_covers, stage_to_chapter
from agents.player_agent import PlayerAgent


def test_library_loads_nine_roles(scenario_dir):
    lib = BookletLibrary(scenario_dir)
    assert lib.public["id"] == "public"
    assert "investigator" in lib.roles
    for i in range(1, 9):
        assert f"char_{i:02d}" in lib.roles


def test_drip_covers(scenario_dir):
    lib = BookletLibrary(scenario_dir)
    a = lib.visible_pack("char_03", 1, include_faction=True)
    assert a["unlocked"] == ["A"]
    assert "B" not in a["covers"]
    assert a["faction"] == "swayable"
    b = lib.visible_pack("char_03", 2)
    assert b["unlocked"] == ["A", "B"]
    assert "周三加更" in b["covers"]["B"]["tonight"]
    c = lib.visible_pack("char_03", 3)
    assert c["unlocked"] == ["A", "B", "C"]


def test_catalog_has_no_faction_or_secret(scenario_dir):
    lib = BookletLibrary(scenario_dir)
    blob = str(lib.catalog())
    assert "pollution" not in blob
    assert "矩阵" not in blob
    assert "周三加更" not in blob


def test_no_boss_layer_in_any_booklet(scenario_dir):
    lib = BookletLibrary(scenario_dir)
    prompt = " ".join(lib.agent_prompt(rid, 3) for rid in lib.role_ids())
    assert "假失踪" not in prompt
    assert "指认：DM" not in prompt
    assert "你们破的局" not in prompt


def test_stage_to_chapter_aligns_frontend():
    assert stage_to_chapter("break_ice") == 1
    assert stage_to_chapter("investigate") == 1
    assert stage_to_chapter("round_table") == 2
    assert stage_to_chapter("accuse") == 3
    assert chapter_to_covers(1) == ("A",)


def test_player_agent_ice_is_chat(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide("char_03", stage="break_ice",
                     legal=["chat", "advance"], use_llm=False)
    assert d["type"] == "chat"
    assert d["source"] == "heuristic"
    text = d["payload"]["text"]
    assert "矩阵" not in text
    assert "周三加更" not in text


def test_player_agent_investigate_searches_hint(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide("investigator", stage="investigate",
                     legal=["chat", "search", "advance"], use_llm=False)
    assert d["type"] == "search"
    assert d["payload"]["location"] in ("档案室", "监控室", "看山工位")


def test_player_agent_never_says_banned_on_ice(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide("char_01", stage="break_ice", legal=["chat"], use_llm=False)
    assert "矩阵" not in d["payload"]["text"]


def test_apply_action_rejects_ai_without_flag(fresh_driver):
    eng, _ = fresh_driver()
    session = eng.create_session("main", "player:1")
    ev, err = eng.apply_action(session, "chat", "ai:char_03",
                               {"text": "hi", "target": "char_01"})
    assert ev == []
    assert err and "player:" in err


def test_apply_action_allows_ai_with_flag(fresh_driver):
    eng, _ = fresh_driver()
    session = eng.create_session("main", "player:1")
    ev, err = eng.apply_action(
        session, "chat", "player:ai:char_03",
        {"text": "我是流量酱。#先认识一下#", "target": "char_01"},
        allow_ai=True)
    assert err is None
    assert any(e.get("type") == "chat" for e in ev)


def test_player_agent_ice_never_advances_when_chat_allowed(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide("char_03", stage="break_ice",
                     legal=["chat", "advance"], use_llm=False)
    assert d["type"] == "chat"
    assert "faction" not in d
    assert "faction" not in (d.get("payload") or {})
    style = "#"
    assert style in d["payload"]["text"]


def test_player_agent_advance_only_when_sole_legal(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide("char_03", stage="break_ice",
                     legal=["advance"], use_llm=False)
    assert d["type"] == "advance"


def test_player_agent_ice_scrubs_never_say_and_must_not(scenario_dir):
    from agents.player_agent import _cover_bans, _scrub_chat
    from engine.booklet import BookletLibrary
    lib = BookletLibrary(scenario_dir)
    pack = lib.visible_pack("char_01", 1, include_faction=True)
    hints = lib.merged_hints("char_01", 1)
    dirty = "我自称矩阵，周三加更，矩阵这个词还承认改过别人的记忆"
    clean = _scrub_chat(dirty, pack, hints)
    for phrase in _cover_bans(pack, hints):
        assert phrase not in clean
    assert "矩阵" not in clean
    assert "周三加更" not in clean


def test_player_agent_investigate_counsels_held_card(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide(
        "investigator", stage="investigate",
        legal=["chat", "search", "counsel", "skill", "advance"],
        state={"held_cards": ["kc_01"], "other_chars": ["char_02"]},
        use_llm=False)
    assert d["type"] == "counsel"
    assert d["payload"]["card"] == "kc_01"
    assert d["payload"]["target"] == "char_02"


def test_player_agent_investigate_skill_when_no_search(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide(
        "investigator", stage="investigate",
        legal=["chat", "skill", "advance"],
        state={"held_cards": [], "other_chars": ["char_01"]},
        use_llm=False)
    assert d["type"] == "skill"
    assert d["payload"]["skill"] in ("draw_card", "truth_check")


def test_player_agent_round_table_prefers_skill(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    inv = agent.decide(
        "investigator", stage="round_table",
        legal=["chat", "skill", "advance"],
        state={"other_chars": ["char_04"]},
        use_llm=False)
    assert inv["type"] == "skill"
    assert inv["payload"]["skill"] == "memory_fix"
    assert inv["payload"]["target"] == "char_04"
    other = agent.decide(
        "char_03", stage="round_table",
        legal=["chat", "skill", "advance"],
        use_llm=False)
    assert other["type"] == "skill"
    assert other["payload"]["skill"] == "draw_card"


def test_player_agent_accuse_votes_with_evidence_cap(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide(
        "investigator", stage="accuse",
        legal=["vote", "advance"],
        state={"other_chars": ["char_01"],
               "evidence": ["clue_a", "clue_b", "clue_c"]},
        use_llm=False)
    assert d["type"] == "vote"
    assert d["payload"]["target"] == "char_01"
    assert d["payload"]["evidence"] == ["clue_a", "clue_b"]


def test_player_agent_accuse_votes_without_evidence(scenario_dir):
    agent = PlayerAgent.from_scenario(scenario_dir)
    d = agent.decide(
        "char_03", stage="accuse",
        legal=["vote", "advance"],
        state={"other_chars": ["char_01"], "evidence": []},
        use_llm=False)
    assert d["type"] == "vote"
    assert d["payload"]["evidence"] == []


def test_player_agent_llm_failure_falls_back(scenario_dir):
    class Boom:
        def chat(self, *args, **kwargs):
            raise RuntimeError("gateway down")

    agent = PlayerAgent.from_scenario(scenario_dir, gateway=Boom())
    d = agent.decide("char_03", stage="break_ice",
                     legal=["chat", "advance"], use_llm=True)
    assert d["type"] == "chat"
    assert d["source"] == "heuristic"


def test_player_agent_llm_advance_rejected_when_chat_legal(scenario_dir):
    class Adv:
        def chat(self, *args, **kwargs):
            return '{"type":"advance","payload":{},"reason":"x"}'

    agent = PlayerAgent.from_scenario(scenario_dir, gateway=Adv())
    d = agent.decide("char_03", stage="break_ice",
                     legal=["chat", "advance"], use_llm=True)
    assert d["type"] == "chat"
    assert d["source"] == "heuristic"


def test_schema_booklets(game_root, scenario_dir):
    import json
    example = json.loads(
        (game_root / "schemas" / "booklet.example.json").read_text(encoding="utf-8"))
    files = sorted((scenario_dir / "booklets").glob("*.json"))
    assert len(files) == 10
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for k in example:
            assert k in data, f"{f.name} 缺少 {k}"
        for letter in ("A", "B", "C"):
            assert letter in data["covers"]
            for field in ("title", "you_are", "tonight", "task", "never_say", "play_hints"):
                assert field in data["covers"][letter], f"{f.name} {letter}.{field}"
