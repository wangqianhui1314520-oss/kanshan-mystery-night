"""G 原矩阵③b：起服端到端 —— 真实 uvicorn 进程（ZHIHU_GAME_USE_MOCK_ENGINE=0）
跑单人三幕全流程：全员心晴分支（REST 全链路）+ boss 链现状取证。

服务为被测对象（subprocess 起停）；会话落盘为 game/data/ 运行时产物（与 F 自检同口径，非源码改动）。
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.conftest import GAME_ROOT

pytestmark = pytest.mark.e2e

PORT = 8917
BASE = f"http://127.0.0.1:{PORT}"
CULPRIT = "char_01"


def _venv_python() -> str:
    """优先 envs/default venv（任务指定）；否则当前解释器。"""
    venv = Path(r"C:\Users\Administrator\.workbuddy\binaries\python\envs"
                r"\default\Scripts\python.exe")
    return str(venv) if venv.exists() else sys.executable


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="module")
def live_server():
    """起服：uvicorn 子进程（真实引擎），健康检查就绪后 yield BASE。"""
    if not _port_free(PORT):
        pytest.skip(f"端口 {PORT} 被占用（可能有残留服务进程）")
    env = dict(os.environ)
    env["ZHIHU_GAME_USE_MOCK_ENGINE"] = "0"
    # 零网络隔离：本 E2E 测的是真实引擎 + REST 链路，不应依赖外部凭证。
    # 若 .env 的 ZHIHU_ACCESS_SECRET 泄入服务进程，每个真人动作后的
    # ai_wave（≤3 空席 × dry_run+apply）与 chat 演出层都会真调 zhida-agent
    # ——单请求延迟远超客户端 10s 超时，且白烧每日直答额度。
    # 空值压过 .env（main.py load_dotenv override=False）→ _llm_for_session
    # 返回 None → 空席走启发式决策，确定性且快。
    for _k in ("ZHIHU_APP_KEY", "ZHIHU_ACCESS_SECRET", "ZHIHU_LLM_MODEL",
               "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        env[_k] = ""
    proc = subprocess.Popen(
        [_venv_python(), "-m", "uvicorn", "server.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(GAME_ROOT), env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        deadline = time.time() + 30
        ready = False
        while time.time() < deadline:
            try:
                r = httpx.get(f"{BASE}/api/health", timeout=2)
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
        if not ready:
            pytest.fail("服务 30s 内未就绪")
        yield BASE
    finally:
        if proc.poll() is None:
            if hasattr(signal, "CTRL_BREAK_EVENT"):
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def _act(c: httpx.Client, sid: str, typ: str, actor: str = "player:1",
         **payload) -> dict:
    r = c.post(f"{BASE}/api/session/{sid}/action",
               json={"type": typ, "actor": actor, "payload": payload})
    r.raise_for_status()
    return r.json()


def _ending(resp: dict) -> dict | None:
    return next((e for e in resp["events"] if e["type"] == "ending"), None)


class TestLiveServerE2E:
    def test_health_engine_mode_real(self, live_server):
        """起服验证：真实引擎模式（mock 关闭）、内容池就绪。"""
        h = httpx.get(f"{BASE}/api/health", timeout=5).json()
        assert h["status"] == "ok"
        assert h["engine"]["mode"] == "engine"
        assert h["engine"]["mock_enabled"] is False
        assert h["engine"]["available"] is True

    def test_create_session_full_scale(self, live_server):
        c = httpx.Client(timeout=10)
        s = c.post(f"{BASE}/api/session",
                   json={"mode": "main", "player_id": "player:1"}).json()
        assert s["ok"] and s["session"]["engine"] == "engine_v3"
        assert s["session"]["clue_pool_size"] == 34
        assert len(s["session"]["npcs"]) == 8
        assert all("faction" not in n for n in s["session"]["npcs"])
        assert all("faction" not in p for p in s["session"].get("players") or [])
        welcome = next(e for e in s["events"] if e["type"] == "system")
        assert welcome["payload"]["event"] == "session_created"
        c.close()

    def test_all_hearts_clear_branch_via_rest(self, live_server):
        """全员心晴分支（REST 全链路）：搜证抽满卡 → 开导 4 人 → 指认幕投错误
        目标（hit=False）→ 结局矩阵 counsel≥4 分支 → 隐藏·全员心晴。"""
        c = httpx.Client(timeout=10)
        sid = c.post(f"{BASE}/api/session",
                     json={"mode": "main", "player_id": "player:1"}
                     ).json()["session"]["session_id"]
        _act(c, sid, "advance")  # → investigate
        locs = [("看山工位", "鱼干"), ("档案室", "经费"), ("茶水间", "泡面"),
                ("空调机房", "门禁"), ("快递柜", "快递"), ("天台", "风"),
                ("监控室", "监控"), ("服务器机房", "机房"), ("热搜后台", "热搜"),
                ("前台", "访客")]
        for loc, kw in locs:  # 10 次搜证（10AP）→ 全队抽满 10 卡
            _act(c, sid, "search", location=loc, keyword=kw)
        _act(c, sid, "advance")  # → round_table
        # 心晴 ×4：按服务端 held_cards 选 char 绑定卡开导（2AP × 4 = 8AP ≤ 9）
        view = c.get(f"{BASE}/api/session/{sid}").json()["session"]
        held = set(view["held_cards"])
        counseled = set()
        card_map = {}
        from tests.conftest import SCENARIO_DIR
        for f in sorted((SCENARIO_DIR / "knowledge_cards").glob("*.json")):
            card = __import__("json").loads(f.read_text(encoding="utf-8"))
            card_map[card["id"]] = card
        for cid in sorted(held):
            binds = str(card_map[cid].get("binds", ""))
            if binds.startswith("char_") and binds not in counseled \
                    and len(counseled) < 4:
                resp = _act(c, sid, "counsel", card=cid, target=binds)
                assert any(e["type"] == "counsel_result" and e["payload"]["matched"]
                           for e in resp["events"]), f"{cid} 开导未命中"
                counseled.add(binds)
        assert len(counseled) == 4, f"开导不足 4 人：{counseled}"
        _act(c, sid, "advance")  # → accuse
        # 投非真凶（hit=False）→ 矩阵落到 counsel≥4 分支
        wrong = next(n["id"] for n in view["npcs"] if n["id"] != CULPRIT)
        resp = _act(c, sid, "vote", target=wrong)
        ending = _ending(resp)
        assert ending is not None
        assert ending["payload"]["outcome"] == "all_hearts_clear"
        assert ending["payload"]["counsel_settlement"]["counsel_count"] == 4
        assert ending["payload"]["counsel_settlement"]["hidden_unlock"] is True
        assert resp["session"]["status"] == "ended"
        c.close()

    def test_boss_chain_rest_g04_fixed_truth_revealed(self, live_server):
        """G04 修复后回归（REST）：唤醒词+双搜证+kc_06 链 = 4/5 破绽 → 指认 DM
        → 终局复盘注入第 5 破绽（review:credits）→ 5/5 → 心晴 1<2 → truth_revealed。"""
        import json
        c = httpx.Client(timeout=10)
        sid = c.post(f"{BASE}/api/session",
                     json={"mode": "main", "player_id": "player:1"}
                     ).json()["session"]["session_id"]
        _act(c, sid, "chat", text="看山，关门")  # flaw flavor_4（0AP）
        _act(c, sid, "advance")                  # → investigate（12AP）
        _act(c, sid, "search", location="看山工位", keyword="鱼干")   # flaw flavor_1
        _act(c, sid, "search", location="监控室", keyword="监控")     # flaw flavor_2
        # 抽卡直至 kc_06 → counsel → clue_030（flaw flavor_3）
        held = set()
        for _ in range(8):
            view = c.get(f"{BASE}/api/session/{sid}").json()["session"]
            held = set(view["held_cards"])
            if "kc_06" in held or view["actions_left"] < 3:
                break
            _act(c, sid, "search", location="茶水间", keyword="泡面")
        assert "kc_06" in held, f"抽卡未出 kc_06（seed 漂移？held={held}）"
        r30 = _act(c, sid, "counsel", card="kc_06", target="char_05")
        assert any(e["payload"].get("clue_id") == "clue_030"
                   for e in r30["events"]), "开导 kc_06 未当场发放 clue_030"
        view = c.get(f"{BASE}/api/session/{sid}").json()["session"]
        assert view["flaw_count"] == 4 and view["boss_ready"] is False
        _act(c, sid, "advance")
        _act(c, sid, "advance")  # → accuse
        resp = _act(c, sid, "vote", target="dm")
        ending = _ending(resp)
        assert ending["payload"]["accused"] == "dm"
        # G04 修复：终局复盘注入使破绽 5/5，boss 裁决放行；心晴 1<2 → truth_revealed
        assert ending["payload"]["outcome"] == "truth_revealed"
        assert ending["payload"]["detail"]["flaw_count"] == 5
        assert ending["payload"]["detail"]["vote_result"]["allowed"] is True
        c.close()

    def test_boss_chain_ultimate_via_rest(self, live_server):
        """设计契约：5 破绽 + 心晴≥2 → 指认 DM → 终极·看山还是山（G04 修复后走通）。"""
        c = httpx.Client(timeout=10)

        def act_safe(typ, actor="player:1", **payload):
            try:
                r = c.post(f"{BASE}/api/session/{sid}/action",
                           json={"type": typ, "actor": actor, "payload": payload})
                return r.status_code, (r.json() if r.content else {})
            except Exception:
                return 0, {}

        sid = c.post(f"{BASE}/api/session",
                     json={"mode": "main", "player_id": "player:1"}
                     ).json()["session"]["session_id"]
        act_safe("chat", text="看山，关门")            # flavor_4（0AP）
        act_safe("advance")                            # → investigate
        act_safe("search", location="看山工位", keyword="鱼干")   # flavor_1
        act_safe("search", location="监控室", keyword="监控")     # flavor_2
        # 抽卡：搜到 kc_06 并开导（flavor_3），同时积累 char 绑定卡供心晴≥2
        bound, saw_kc06, kc06_done, done = {}, False, False, 0
        for _ in range(28):
            view = c.get(f"{BASE}/api/session/{sid}").json()["session"]
            if view["actions_left"] < 2:
                act_safe("advance")                    # 轮循环/推幕刷新 AP
            st, out = act_safe("search", location="茶水间", keyword="泡面")
            for e in out.get("events", []):
                if e["type"] == "system" and e["payload"].get("event") == "card_drawn":
                    card = e["payload"]["card"]
                    if str(card.get("binds", "")).startswith("char_"):
                        bound[card["id"]] = card["binds"]
                    if card.get("id") == "kc_06":
                        saw_kc06 = True
            view = c.get(f"{BASE}/api/session/{sid}").json()["session"]
            if saw_kc06 and "kc_06" in view["held_cards"] and not kc06_done:
                st, out = act_safe("counsel", card="kc_06", target="char_05")
                kc06_done = any(e["type"] == "counsel_result" and e["payload"].get("matched")
                                for e in out.get("events", []))
            if kc06_done and done >= 2:
                break
        assert saw_kc06 and kc06_done, f"kc_06 链未走通：saw={saw_kc06} done={kc06_done}"
        # 心晴≥2：绑定卡逐一匹配开导（跳过 kc_06 已计）
        done = 0
        for cid, ch in bound.items():
            if cid == "kc_06":
                continue  # kc_06 的 matched 已在搜索循环计数
            st, out = act_safe("counsel", card=cid, target=ch)
            done += sum(1 for e in out.get("events", [])
                        if e["type"] == "counsel_result" and e["payload"].get("matched"))
            if done >= 2:
                break
        # 推进到 accuse（round_table 循环耗幕轮数）
        for _ in range(6):
            view = c.get(f"{BASE}/api/session/{sid}").json()["session"]
            if view["stage"] == "accuse":
                break
            if view["status"] != "playing":
                break
            act_safe("advance")
            act_safe("advance")
        view = c.get(f"{BASE}/api/session/{sid}").json()["session"]
        assert view["stage"] == "accuse", f"未进入指认幕：{view['stage']}"
        st, out = act_safe("vote", target="dm")
        ending = _ending(out)
        assert ending is not None and ending["payload"]["accused"] == "dm"
        assert ending["payload"]["outcome"] == "kanshan_still_mountain", (
            f"ending={ending['payload'].get('ending')} "
            f"flaw={ending['payload'].get('flaw_count')} "
            f"clinic={ending['payload'].get('clinic')}")
        c.close()


