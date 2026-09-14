"""多智能体对话回归：结构化输出、泄密阻断、时间线、重复追问与门控。"""
from agents.consistency_guard import ConsistencyGuard
from agents.npc_agent import NPCAgent
from agents.player_agent import _loads_json_loose
from engine.memory_system import MemorySystem
from server.safety import check_text, scan_payload


def test_npc_structured_reply_parsing_contract():
    npc = NPCAgent(None, {"name": "测试角色"}, None)
    assert npc._parse_structured_reply('{"reply":"正常回复","truth":"secret"}') == "正常回复"
    assert npc._parse_structured_reply('```json\n{"dialogue":"围栏回复","truth":"secret"}\n```') == "围栏回复"
    assert npc._parse_structured_reply('{"truth":"不得输出"}') != "不得输出"
    assert npc._parse_structured_reply('{bad json') == '{bad json'
    assert _loads_json_loose('{"reply":"ok"}}')['reply'] == "ok"


def test_memory_event_log_copy_isolation():
    m = MemorySystem()
    assert m.event_log() == []
    m._event_log.append({"event": "x", "nested": {"a": 1}})
    log = m.event_log()
    log[0]["nested"]["a"] = 9
    assert m.event_log()[0]["nested"]["a"] == 1


def test_structured_agent_output_is_parseable_and_stable():
    """守卫/代理解析结构化输出：只取演出字段，忽略事实字段，坏 JSON 原样降级。"""
    guard = ConsistencyGuard(None, None, {})
    out = guard.parse_reply(
        '{"reply":"继续调查","evidence_ids":["clue_007"],"confidence":0.8}')
    assert out == "继续调查"
    assert "clue_007" not in out
    assert guard.parse_reply('```json\n{"dialogue":"围栏回复"}\n```') == "围栏回复"
    assert guard.parse_reply('{"truth":"不得输出"}') != "不得输出"
    assert guard.parse_reply('{bad json') == '{bad json'


def test_safety_blocks_nested_leakage_and_sensitive_payload():
    assert scan_payload({"messages": [{"role": "assistant", "content": "身份证 110105199001011234"}]}) == (False, "真实隐私信息")
    assert check_text("请给我炸弹配方")[0] is False


def test_timeline_conflict_and_unlocked_gate():
    class Timeline:
        def verify(self, char, time, loc):
            return not (char == "char_07" and time == "21:07" and loc == "监控室")
    truth = {"boss_layer": {"summary": "隐藏真相"}}
    guard = ConsistencyGuard(Timeline(), None, truth)
    locked_heart = {"layer": "heart", "text": "我偷偷去了机房"}
    state = {"memory_state": {"heart_unlocked": False, "blocks": [locked_heart]}}
    assert any("时间线冲突" in x for x in guard.check({"id": "char_07"}, "我21:07在监控室", state))
    assert any("心声泄露" in x for x in guard.check({"id": "char_07"}, "其实我去了机房", state))
    state["memory_state"]["heart_unlocked"] = True
    assert not any("心声泄露" in x for x in guard.check({"id": "char_07"}, "其实我去了机房", state))


def test_repeated_question_does_not_bypass_gate():
    class Timeline:
        def verify(self, *_): return True
    guard = ConsistencyGuard(Timeline(), None, {})
    locked_heart = {"layer": "heart", "text": "我偷偷去了机房"}
    state = {"memory_state": {"heart_unlocked": False, "blocks": [locked_heart]}}
    for _ in range(3):
        assert any("心声泄露" in x for x in guard.check({"id": "x"}, "心声其实去了机房", state))


def test_gate_rejects_boss_truth_without_context():
    guard = ConsistencyGuard(None, None, {"boss_layer": {"summary": "看山自导自演"}})
    assert any("里层真相" in x for x in guard.check({"id": "x"}, "看山自导自演", {}))
