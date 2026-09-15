"""服务入口：FastAPI + WebSocket 房间。

契约（冻结，不得改路径与事件结构）：
- docs/CONTRACTS.md §3.6 WS 事件协议：
  事件 = {"type","session_id","round","actor","payload"}；
  client→server 仅 search/chat/skill/counsel/vote/advance；
- §3.7 REST 路由：
  POST /api/session · GET /api/session/{id} · POST /api/session/{id}/action ·
  WS /ws/{session_id} · GET /api/health。
  语音信令（非 §3.6，不进引擎）：WS /ws/{session_id}/voice ·
  GET /api/session/{id}/voice/ice-servers。

硬规则：
- 凭证仅经环境变量（ZHIHU_ACCESS_SECRET 等），不落代码/前端/文档；
- API 失败给真实降级提示，不伪造内容（见 gateway 降级信封）；
- 引擎未就绪时用可开关 mock 状态机（ZHIHU_GAME_USE_MOCK_ENGINE，默认开）；
- GameServer 保留骨架签名（__init__ / on_connect / handle），实现归 F 窗口。

启动：cd game && python -m uvicorn server.main:app --host 127.0.0.1 --port 8899
"""
import asyncio
import copy
import json
import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

# 凭证注入：部署/本地启动时从 game/.env 读取（仅在环境变量未设时填充）。
# dotenv 缺失不阻止服务启动，但保留可诊断状态，避免 AI 未配置原因被静默吞掉。
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_DOTENV_STATUS = {"available": False, "loaded": False, "error": ""}
try:
    from dotenv import load_dotenv
    _DOTENV_STATUS["available"] = True
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=False)
        _DOTENV_STATUS["loaded"] = True
except Exception as exc:
    _DOTENV_STATUS["error"] = type(exc).__name__
    import logging
    logging.getLogger(__name__).warning(
        "python-dotenv unavailable; game/.env was not loaded (%s)", type(exc).__name__)

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Windows 本机系统代理可能把 localhost/回环与出网请求送进代理，造成 502/405。
# 服务端所有 HTTP 出站统一直连；各 httpx 调用仍显式 trust_env=False。
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from .gateway.zhihu_gateway import ZhihuGateway
from .mock_engine import CLIENT_ACTIONS, MockStateMachine, make_event, mock_enabled
from .oauth import ZhihuOAuth
from .reply_guard import RETRY_HINT, has_product_identity
from .safety import ContentSafetyMiddleware, check_text
from .scenario_resolve import (resolve_session_scenario_dir,
                               validate_scenario_for_session)
from .store.session_store import SessionStore
from .voice_hub import VoiceHub, ice_servers_from_env

GAME_ROOT = Path(__file__).resolve().parent.parent
if str(GAME_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(GAME_ROOT))
try:
    from studio import generate, list_book_covers, list_jobs, load_job
    from studio import load_player_book, public_snapshot
    from studio.tiers import PRESET_SEEDS
    _STUDIO_IMPORT_ERROR: str | None = None
except Exception as _e:
    generate = load_job = list_jobs = public_snapshot = None  # type: ignore[assignment]
    load_player_book = list_book_covers = None  # type: ignore[assignment]
    PRESET_SEEDS = ()
    _STUDIO_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

# 引擎适配层导入容错：其他窗口对 engine/ 的并发编辑中间态不应拖垮服务。
try:
    from .engine_driver import EngineDriver, LOC_ALIASES
    _ENGINE_IMPORT_ERROR: str | None = None
except Exception as _e:  # ImportError/SyntaxError 等一律如实记录
    EngineDriver = None  # type: ignore[assignment, misc]
    LOC_ALIASES = {}
    _ENGINE_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

# AgentRuntime（agents/bridge.py，契约 §3.5c）：driver 裁决、rt 演出——并存
try:
    from agents.bridge import AgentRuntime, bootstrap
    _RT_IMPORT_ERROR: str | None = None
except Exception as _e:
    AgentRuntime = None  # type: ignore[assignment, misc]
    _RT_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"

RT_SKILL_FLOWS = ("collect", "bid_headline", "stealth_photo",
                  "share_photo", "cross_check",
                  "puzzle")  # 走 rt *_flow 的技能（rt 自有状态裁决）

SCENARIO_DIR = GAME_ROOT / "content" / "scenarios" / "kanshan"
DATA_DIR = GAME_ROOT / "data"

VALID_MODES = ("main", "daily", "quick", "party")  # v2.1：+party 多人同场

# 房间码 → session_id 映射（内存态；6 位码是给真人口头/链接分享的短标识，
# 真实房间 id 仍是长 session_id）。服务重启后可由 SessionStore 扫描重建。
ROOM_CODE_INDEX: dict[str, str] = {}


def engine_mode() -> str:
    """引擎选择：ZHIHU_GAME_USE_MOCK_ENGINE=1 → mock；默认（0/未设）→ 真实引擎。"""
    return "mock" if mock_enabled() else "engine"


class GameServer:
    """WebSocket 房间管理（骨架签名保持：__init__ / on_connect / handle）。"""

    def __init__(self, scenario_dir: Path):
        self.scenario_dir = scenario_dir
        self.rooms = {}  # room_id -> {"sockets": set[WebSocket]}
        # 以下为骨架外新增依赖（create_app 生命周期注入）：
        self.store: SessionStore | None = None
        self.gateway: ZhihuGateway | None = None
        self.oauth: ZhihuOAuth | None = None
        self.engine: MockStateMachine | None = None
        self.engines: dict[str, EngineDriver] = {}  # session_id -> 真实引擎实例（进程内缓存）
        self.mock_engines: dict[str, MockStateMachine] = {}  # scenario 路径 -> mock 实例
        self.runtimes: dict = {}  # session_id -> AgentRuntime（rt 演出层，契约 §3.5c）
        self.oauth_tokens: dict[tuple[str, str], dict] = {}  # (sid, player) -> token（仅内存，不落盘）
        # 按对局隔离动作锁。原先使用单个全局锁，会让一个房间的 AI wave
        # 阻塞所有其他房间；同时仍保证同一 session 的读改写原子性。
        self._action_locks: dict[str, asyncio.Lock] = {}
        self._ai_waving = False  # run_ai_wave 重入保护（allow_ai=True 路径不再 wave）
        self._ws_action_tasks: set[asyncio.Task] = set()

    def _action_lock_for(self, session_id: str) -> asyncio.Lock:
        """返回指定对局的锁；锁只在进程内存在，不写入 session。"""
        lock = self._action_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._action_locks[session_id] = lock
        return lock

    def _drop_action_lock(self, session_id: str) -> None:
        """对局结束后释放锁引用，避免长时间运行的服务内存增长。"""
        lock = self._action_locks.get(session_id)
        if lock is not None and not lock.locked():
            self._action_locks.pop(session_id, None)

    async def _run_ws_action(self, ws, session_id: str, action_type: str,
                             actor: str, payload: dict) -> None:
        """后台完成 WS 动作；AI 回复不能占住该连接的收包循环。"""
        try:
            _, error = await self.run_action(session_id, action_type, actor, payload)
            if error is not None:
                await self._send_error(ws, session_id, error["notice"])
        except Exception as exc:  # pragma: no cover - 连接断开时仅做兜底
            await self._send_error(ws, session_id, f"动作处理异常：{type(exc).__name__}: {exc}")

    def _spawn_ws_action(self, ws, session_id: str, action_type: str,
                         actor: str, payload: dict) -> None:
        task = asyncio.create_task(
            self._run_ws_action(ws, session_id, action_type, actor, payload))
        self._ws_action_tasks.add(task)
        task.add_done_callback(self._ws_action_tasks.discard)

    # ------------------------------------------------------------- 房间管理
    async def on_connect(self, ws, room_id: str):
        """新玩家加入对局房间（签名保持）；player_id/spectator 由 ws.state 携带。"""
        room = self.rooms.setdefault(room_id, {"sockets": set(), "players": {}})
        room["sockets"].add(ws)
        player_id = getattr(ws.state, "player_id", None)
        if player_id and not getattr(ws.state, "spectator", False):
            room["players"][player_id] = ws
        ws.state.room_id = room_id

    def on_disconnect(self, ws, room_id: str):
        room = self.rooms.get(room_id)
        if room:
            room["sockets"].discard(ws)
            player_id = getattr(ws.state, "player_id", None)
            if player_id and room["players"].get(player_id) is ws:
                room["players"].pop(player_id, None)

    async def broadcast_to(self, room_id: str, player_ids, events):
        """定向广播（真人私聊路由用）：仅发给指定玩家的 WS 连接。"""
        room = self.rooms.get(room_id)
        if not room:
            return
        targets = {player_ids} if isinstance(player_ids, str) else set(player_ids)
        for pid in targets:
            ws = room["players"].get(pid)
            if ws is None:
                continue
            for evt in events:
                try:
                    await ws.send_text(json.dumps(evt, ensure_ascii=False))
                except Exception:
                    room["sockets"].discard(ws)

    # --------------------------------------------------------- 引擎实例管理
    def get_mock_engine(self, session: dict) -> MockStateMachine:
        """按 session.scenario_id 取 mock 状态机（多剧本缓存）。"""
        path = resolve_session_scenario_dir(session.get("scenario_id"))
        key = str(path)
        eng = self.mock_engines.get(key)
        if eng is None:
            eng = MockStateMachine(path, self.store)
            self.mock_engines[key] = eng
        return eng

    def get_engine(self, session: dict) -> EngineDriver:
        """取（或按 actions 日志回放重建）该对局的真实引擎实例。"""
        sid = session["session_id"]
        eng = self.engines.get(sid)
        if eng is not None:
            return eng
        scenario_path = resolve_session_scenario_dir(session.get("scenario_id"))
        eng = EngineDriver(scenario_path)
        snap = session.get("party")
        if snap:
            eng.restore_party(snap)  # PartyBoard 恢复（发牌/席位/AP/票池）
        replay = list(session.get("actions", []))
        session["actions"] = []  # apply_action 会重新积累，避免重复追加
        was_ended = session.get("status") != "playing"
        session["status"] = "playing"  # 终局档回放：临时解闸，末尾动作自然回到终态
        for act in replay:  # 确定性回放（引擎无 AI 参与）
            eng.apply_action(session, act["type"], act["actor"], act["payload"])
        if was_ended and session.get("status") == "playing":
            session["status"] = "ended"  # 兜底：日志无终局动作（异常档）
        self.engines[sid] = eng
        return eng

    # ------------------------------------------ rt 演出层（契约 §3.5c 并存）
    def get_runtime(self, session: dict):
        """取（或建）该对局的 AgentRuntime；首次构建按 session 事件流回喂计数。"""
        if AgentRuntime is None:
            return None
        sid = session["session_id"]
        rt = self.runtimes.get(sid)
        if rt is None:
            host = next((p["player_id"] for p in session.get("players", [])),
                        "player:1")
            # 所有 Agent（DM/NPC/法官/AI 坐席）统一复用知乎直答通道；
            # 规则引擎仍独立裁决，模型只负责演出与行动意图。
            cfg = (getattr(app.state, "api_cfg", {}) or {}).get(sid) or {}
            if cfg.get("llm_key"):
                os.environ["LLM_API_KEY"] = cfg["llm_key"]
                if cfg.get("llm_base"):
                    os.environ["LLM_BASE_URL"] = cfg["llm_base"]
                if cfg.get("llm_model"):
                    os.environ["LLM_MODEL"] = cfg["llm_model"]
            llm = self._llm_for_session(sid)
            scenario_path = resolve_session_scenario_dir(session.get("scenario_id"))
            rt = AgentRuntime(scenario_path, llm=llm, session_id=sid, player_id=host)
            self.runtimes[sid] = rt
            self._feed_rt_from_session(rt, session)  # 成就判定素材连续性
        return rt

    def _llm_for_session(self, session_id: str):
        """有完整 LLM 配置则建 LLMClient（设置面板 header / .env），否则 None 走启发式+skill。"""
        cfg = (getattr(app.state, "api_cfg", {}) or {}).get(session_id) or {}
        key = cfg.get("llm_key") or os.environ.get("LLM_API_KEY") or ""
        base = (cfg.get("llm_base") or os.environ.get("LLM_BASE_URL") or "").rstrip("/")
        model = cfg.get("llm_model") or os.environ.get("LLM_MODEL") or ""
        # 比赛统一要求：无论设置面板是否残留自定义模型配置，均优先使用知乎官方 Agent。
        zhihu_secret = (cfg.get("zhihu_secret") or os.environ.get("ZHIHU_APP_KEY")
                        or os.environ.get("ZHIHU_ACCESS_SECRET") or "")
        # ZHIHU_AI_DEFAULT=0 供测试隔离（conftest autouse 设置）：回退通道不再
        # 把知乎凭证写进进程 env，避免污染"无配置"断言与后续 fixture。
        zhihu_default_on = os.environ.get("ZHIHU_AI_DEFAULT", "1") not in (
            "0", "", "false", "False")
        if zhihu_secret and zhihu_default_on:
            if self.gateway is not None:
                self.gateway.access_secret = zhihu_secret
            if not (key and base and model):
                # NPC/坐席高频对话统一走 LLMClient(zhida-agent)：网关 chat 的
                # 默认 fast 模型不能扮演角色、且直答点睛限额仅 2/日，
                # 网关只留给每日导读等低频高光位。
                key = zhihu_secret
                base = "https://developer.zhihu.com/v1"
                model = cfg.get("llm_model") or os.environ.get("ZHIHU_LLM_MODEL", "zhida-agent")
        if not (key and base and model):
            return None
        panel_main = bool(cfg.get("llm_key") and cfg.get("llm_base")
                          and cfg.get("llm_model"))
        os.environ["LLM_API_KEY"] = key
        os.environ["LLM_BASE_URL"] = base
        os.environ["LLM_MODEL"] = model
        # 统一 AI 通道使用知乎直答 Provider；复用设置面板/赛事注入的官方密钥。
        # 注意：env 即配置（Provider 运行时活读环境），此处有意持久写入；
        # 需要零网络隔离的测试应在各自 fixture 中 delenv ZHIHU_*/LLM_*。
        if "developer.zhihu.com" in base:
            os.environ["ZHIHU_APP_KEY"] = key
        try:
            from agents.llm_client import LLMClient, OpenAICompatProvider, MockProvider
            if panel_main:
                # 用户在面板显式指定自建端点（如 DeepSeek）→ 本对局 AI 全量走
                # main 通道：不注册 zhida 槽位，call_gateway(provider="zhida")
                # 经 _pick 降级自然落 main——否则 env 里的知乎凭证恒可用、
                # zhida 恒优先，面板配置永远不会生效（用户实测复现的根因）。
                return LLMClient(providers={"main": OpenAICompatProvider(),
                                            "mock": MockProvider()})
            return LLMClient()
        except Exception:
            return None

    @staticmethod
    def _feed_rt_from_session(rt, session: dict):
        """按历史事件流回喂 record_event（仅 rt 新建时执行一次，幂等无重复）。"""
        for evt in session.get("events", []):
            GameServer._feed_rt_event(rt, evt)

    @staticmethod
    def _feed_rt_event(rt, evt: dict):
        """把 §3.6 事件翻译为 rt.record_event 记账（成就判定素材）。"""
        try:
            etype, payload = evt.get("type"), evt.get("payload") or {}
            if etype == "clue_gained":
                rt.record_event("search_count")
                if not str(payload.get("clue_id", "")).startswith("env_"):
                    rt.record_event("hit_count")
                else:
                    rt.record_event("env_clue", value=payload.get("name")
                                    or payload.get("clue_id"))
            elif etype == "system" and payload.get("event") == "flaw_progress":
                pass  # 破绽计数以 rt.sync_flaws() 于演出时同步
            elif etype == "system" and payload.get("event") == "difficulty_set":
                pass
            elif etype == "chat":
                pass
            elif etype == "counsel_result" and payload.get("matched"):
                rt.record_event("heart_unlock_count")
            elif etype == "memory_unlock":
                # 深状态同步：driver 解锁版本链 → rt.memory 同步（篡改点发现随之
                # 就位，拼图对质 spend_tamper_points 才可用；C 组交代对接点）
                owner = str(payload.get("owner", "")).replace("npc:", "")
                if owner:
                    rt.unlock_memory(owner, str(payload.get("reason", "memory_fix")))
            elif etype == "system" and payload.get("event") == "refute_result":
                if payload.get("ok"):
                    rt.record_event("fake_exposed")
                    rt.record_event("refute_success_streak")
            elif etype == "ending":
                rt.record_event("ending", value=payload.get("outcome"))
        except Exception:
            pass  # 记账失败不影响裁决事件广播

    def _spend_ap(self, session: dict, actor: str, n: int) -> str | None:
        """AP 扣减（rt flow 前置校验，C 组交代：暗拍 2AP 由上层扣减/校验）。

        party 模式走 PartyBoard 池（各算各的）；单人 engine 档走幕配额池；
        mock 档走 session 计数。成功返回 None，失败返回错误 notice。
        """
        if session.get("mode") == "party" and \
                session.get("engine") == "engine_v3" and EngineDriver is not None:
            try:
                eng = self.get_engine(session)
                if not eng.pb.spend(actor, n):
                    return (f"行动力不足（你剩 {eng.pb.ap_state().get(actor, 0)}，"
                            f"需 {n}）；party 模式每人每轮 3 点")
                session["ap_state"] = eng.pb.ap_state()
                return None
            except Exception as e:
                return f"行动力校验失败：{type(e).__name__}: {e}"
        if session.get("engine") == "engine_v3" and EngineDriver is not None:
            try:
                eng = self.get_engine(session)
                if eng.sm.actions_left < n:
                    return (f"行动力不足（剩 {eng.sm.actions_left}，需 {n}）；"
                            f"可 advance 结束本轮")
                eng.sm.actions_left -= n
                session["actions_left"] = eng.sm.actions_left
                return None
            except Exception as e:
                return f"行动力校验失败：{type(e).__name__}: {e}"
        if session.get("actions_left", 0) < n:
            return f"行动力不足（剩 {session.get('actions_left', 0)}，需 {n}）"
        session["actions_left"] = session.get("actions_left", 0) - n
        return None

    def _rt_skill_flow(self, session: dict, actor: str,
                       payload: dict) -> tuple[list[dict], str | None]:
        """collect / bid_headline 技能 → rt 对应 *_flow（rt 自有状态裁决 + 演出）。"""
        rt = self.get_runtime(session)
        if rt is None:
            return [], (f"AgentRuntime 当前不可导入（agents/ 并发编辑中间态），"
                        f"原因：{_RT_IMPORT_ERROR}")
        sid, rnd = session["session_id"], session.get("round", 1)
        skill = str((payload or {}).get("skill") or (payload or {}).get("kind") or "")
        if skill == "stealth_photo":
            # 暗拍（P2）：2AP 由上层调用前扣减/校验（C 组交代）；线索留原地，仅持照片
            err = self._spend_ap(session, actor, 2)
            if err:
                return [], err
            location = str(payload.get("location", ""))
            location = LOC_ALIASES.get(location, location)
            if session.get("engine") == "engine_v3" and EngineDriver is not None:
                try:  # location 三口径：loc_* / scene_map key → 线索中文名
                    eng = self.get_engine(session)
                    location = eng._loc_names.get(location, location)
                except Exception:
                    pass
            res = rt.stealth_photo_flow(location,
                                        str(payload.get("keyword", "")))
            # owner 隔离（缺口1）：照片归暗拍者本人（rt.player_id 在多人局恒为
            # 房主，此处以 actor 校正归属），前端按 owner 决定私密墙可见性
            photo = res.get("photo")
            if isinstance(photo, dict):
                photo["owner"] = actor
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "stealth_photo_result", "ok": res.get("ok", False),
                "photo": photo, "owner": actor if photo else None,
                "env_note": res.get("env_note"),
                "notice": ("暗拍成功：线索留原地，你持有照片（可分享/可说谎，真伪圆桌对质）"
                           if res.get("ok") else
                           f"暗拍未命中（{res.get('reason', 'no_hit')}）——行动力已扣"),
                "source": "rt"})], None
        if skill == "share_photo":
            # 照片流出（缺口1）：owner 隔离——只能分享自己持有的照片；
            # claim 可说谎，真伪留圆桌对质（引擎 EvidenceChain.share_photo 登记）
            photo_id = str(payload.get("photo_id") or payload.get("photo") or "")
            claim = str(payload.get("claim") or "").strip()[:60] or None
            ec = getattr(rt, "evidence", None)
            res = ec.share_photo(actor, photo_id, claim=claim) if ec is not None else None
            if not res:
                return [], "照片不存在或不归你持有（仅本人暗拍的照片可流出）"
            photo = res.get("photo") or {}
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "photo_shared", "ok": True,
                "photo_id": photo.get("photo_id") or photo_id,
                "clue_id": photo.get("clue_id"), "name": photo.get("name", ""),
                "owner": photo.get("owner") or actor,
                "claim": res.get("claim") or claim or "（未填声称）",
                "notice": "叮——照片已流出。照片是真的，\"声称\"可不一定——圆桌见。",
                "source": "rt"})], None
        if skill == "cross_check":
            # 交叉验证（缺口2）：真伪裁决权威=引擎证据链（tier/fake_of 为剧本静态
            # 数据）；「实锤」判定=持有人已握有 fake_of 指向的真线索——持有口径
            # 用 session clues_gained（mock 与真实引擎两档均可靠同步）兜底
            clue_id = str(payload.get("clue_id") or "")
            ec = getattr(rt, "evidence", None)
            fake = ec.pool.get(clue_id) if ec is not None else None
            if fake is None or ec.tier_of(fake) != "fake":
                return [], "该线索不在伪证池，无需交叉验证"
            real = ec.forgery_target(clue_id)
            held = set(session.get("clues_gained") or [])
            try:  # 真实引擎档：按持有人补齐（ec 与 rt.evidence 状态可能不同步）
                held.update(ec.get_player_clues(actor))
            except Exception:
                pass
            exposed = bool(real) and real.get("id") in held
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "cross_check_result", "ok": True, "clue_id": clue_id,
                "verdict": "exposed" if exposed else "insufficient",
                "exposed": exposed,
                "real_id": (real or {}).get("id"),
                "real_name": (real or {}).get("name"),
                "notice": (f"交叉验证实锤：与《{(real or {}).get('name', '')}》矛盾，"
                           "伪证已标记，圆桌对质主动权在你"
                           if exposed else
                           "交叉验证暂无实锤：尚未持有可对照的真线索，先标记存疑"),
                "source": "rt"})], None
        if skill == "puzzle":
            # 记忆拼图对质：篡改点成本由 rt.puzzle_flow 内部校验（不足返回
            # not_enough_tamper_points，无需预扣——C 组交代）；判定权威=引擎
            proposal = payload.get("proposal") or []
            if not isinstance(proposal, list):
                return [], "proposal 必须为记忆块 id 数组"
            res = rt.puzzle_flow(str(payload.get("target", "")), proposal)
            if not res.get("ok") and res.get("reason") == "not_enough_tamper_points":
                return [make_event("system", sid, rnd, "kanshan", {
                    "event": "puzzle_rejected",
                    "notice": "发起拼图对质需 2 个已发现篡改点（当前不足）——"
                              "先通过记忆修复/知识开导发现记忆出入",
                    "source": "rt"})], None
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "puzzle_result", "correct": res.get("correct"),
                "ok": res.get("ok"), "show": res.get("show"),
                "notice": ("排对全场获线索（线索奖励发放为 C/D 细化边界）"
                           if res.get("correct") else
                           "排错进入 DM 锐评环节"),
                "source": "rt"})], None
        if skill == "collect":
            item_id = str(payload.get("item", "")).strip()
            if not item_id:
                return [], "collect 需要 item（收集品 id，见 content/scenarios 收集品清单）"
            res = rt.collect_flow(item_id)
            return [make_event("system", sid, rnd, "kanshan", {
                "event": "collect_result", "item": item_id,
                "collected": res.get("collected", res.get("ok", False)),
                "all_collected": res.get("all_collected", False),
                "show": res.get("show"),
                "notice": "收集品拾取（彩蛋层，不进证据链、零行动点）",
                "source": "rt"})], None
        # bid_headline：头条明牌竞标（faction 仅内部使用，零透出前端）
        faction = "truth"
        if session.get("engine") == "engine_v3" and EngineDriver is not None:
            try:
                eng = self.get_engine(session)
                eng.pb.assign_factions()
                faction = eng.pb.faction_of(actor) or "truth"
            except Exception:
                faction = "truth"
        amount = int(payload.get("amount", 1) or 1)
        res = rt.headline_flow(actor, faction, amount,
                               topic=payload.get("topic"),
                               post_id=payload.get("post") or None)
        # faction 零透出：bid/settle 引擎原样返回含 faction 顶层字段，白名单化剔除
        bid = {k: v for k, v in (res.get("bid") or {}).items()
               if k not in ("faction",)}
        settle = {k: v for k, v in (res.get("settle") or {}).items()
                  if k not in ("faction", "winner_faction")}
        return [make_event("system", sid, rnd, "dm", {
            "event": "headline_result", "bid": bid,
            "settle": {"ok": settle.get("ok"), "winner": settle.get("winner"),
                       "post_id": settle.get("post_id"),
                       "topic": settle.get("topic")},
            "host_line": res.get("host_line"),
            "result_line": res.get("result_line"),
            "notice": "头条竞标结算完成（明牌竞标，faction 结果不透出）",
            "source": "rt"})], None

    def _rt_ending_flow(self, session: dict, ending_evt: dict) -> list[dict]:
        """终局 → rt.achievements_flow + report_flow（成就/侦探报告演出）。"""
        rt = self.get_runtime(session)
        if rt is None:
            return []
        sid = session["session_id"]
        outcome = ending_evt.get("payload", {}).get("outcome")
        events = []
        try:
            shows = rt.achievements_flow(outcome)
            if not shows:  # 空结果也发审计事件（证明 flow 已被调用，成就判定为引擎权威）
                events.append(make_event("system", sid,
                                         session.get("round", 1), "dm", {
                    "event": "achievements_checked", "unlocked": 0,
                    "notice": "本轮无新解锁成就（AchievementEngine 确定性判定）",
                    "source": "rt"}))
            for show in shows:
                # achievement_show 可能返回 dict（横幅结构）或 str（纯演出文本）——都透出
                payload_a = show if isinstance(show, dict) else {"show": str(show)}
                events.append(make_event("achievement_unlocked", sid,
                                         session.get("round", 1), "kanshan", {
                    "player_id": ending_evt.get("payload", {}).get("accused"),
                    "achievement": payload_a, "source": "rt"}))
            report = rt.report_flow(
                outcome, ending_info=ending_evt.get("payload", {}),
                boss_accused_success=ending_evt.get("payload", {}).get(
                    "outcome") in ("kanshan_still_mountain", "truth_revealed"),
                pollution_win=ending_evt.get("payload", {}).get(
                    "outcome") == "pollution_win",
                most_hammered=(ending_evt.get("payload", {}).get("detail", {})
                               or {}).get("most_hammered"))
            events.append(make_event("system", sid, session.get("round", 1),
                                     "dm", {
                "event": "detective_report",
                "report_text": report.get("report_text", ""),
                "badges": report.get("badges", []),
                "achievements": report.get("achievements", []),
                "notice": "《侦探报告》已生成（前端分享卡素材，只导出图片不做自动发布）",
                "source": "rt"}))
        except Exception as e:  # 演出失败不影响终局裁决事件
            events.append(make_event("system", sid, session.get("round", 1),
                                     "dm", {
                "event": "rt_flow_error",
                "notice": f"演出层生成失败（终局裁决不受影响）：{type(e).__name__}: {e}"}))
        return events

    def _rt_broadcast_accident(self, session: dict) -> list[dict]:
        """心声广播事故（P1）：白名单过滤权归引擎（rt.memory），DM 演出包装。"""
        rt = self.get_runtime(session)
        if rt is None:
            return []
        try:
            text = rt.broadcast_accident_flow()
            if not text:
                return []
            return [make_event("system", session["session_id"],
                               session.get("round", 1), "dm", {
                "event": "broadcast_accident", "text": text,
                "notice": "心声广播事故（白名单外内容已被引擎拦截）", "source": "rt"})]
        except Exception:
            return []

    async def broadcast(self, room_id: str, events):
        """全房间广播（含死连接清理）。"""
        room = self.rooms.get(room_id)
        if not room:
            return
        dead = []
        for ws in list(room["sockets"]):
            for evt in events:
                try:
                    await ws.send_text(json.dumps(evt, ensure_ascii=False))
                except Exception:
                    dead.append(ws)
                    break
        for ws in dead:
            room["sockets"].discard(ws)

    # ------------------------------------------------------------- 统一动作
    async def run_action(self, session_id: str, action_type: str, actor: str,
                         payload: dict, *, allow_ai: bool = False
                         ) -> tuple[list[dict], dict | None]:
        """REST 与 WS 共用的动作管线：校验 → 引擎/mock 结算 → 落库 → 广播。

        返回 (事件列表, 错误信息 dict|None)。错误信息形如 {"notice": ..., "status": ...}。
        """
        mode = engine_mode()
        session = self.store.load_session(session_id)
        if session is None:
            return [], {"status": 404, "notice": f"对局不存在：{session_id}"}
        # 竞态幂等（2026-09-14 后台 wave 化取证）：自走棋 AI 席与真人同权
        # 投票，AI 先投满 → 对局 ended 时玩家的 vote 动作会扑空（引擎拒绝
        # ended 会话）。此时幂等重放已存终局事件，前端仍能正常收尾。
        if session.get("status") == "ended":
            ending = next((e for e in reversed(session.get("events") or [])
                           if e.get("type") == "ending"), None)
            if ending is not None:
                return [ending], None
        # 所有入口（REST、WS、AI 补位）共享的输入边界。ContentSafetyMiddleware
        # 负责危险内容类别，本处负责类型/长度，避免超大提示词拖垮模型与事件日志。
        payload = payload if isinstance(payload, dict) else {}
        if action_type == "chat":
            raw_text = payload.get("text", "")
            if not isinstance(raw_text, str):
                return [], {"status": 400, "notice": "聊天内容必须是文本"}
            if not raw_text.strip():
                return [], {"status": 400, "notice": "聊天内容不能为空"}
            if len(raw_text) > 1000:
                return [], {"status": 413, "notice": "聊天内容过长（最多 1000 字）"}
            ok, reason = check_text(raw_text)
            if not ok:
                return [], {"status": 422, "notice": f"聊天内容包含{reason}，请修改后重试"}
        # 按对局自身 engine 字段路由（老 mock 档继续走 mock，新档走真实引擎）
        use_mock = session.get("engine", "mock") == "mock"
        # 玩家意图仅适配真实引擎的公开聊天；AI 坐席、私聊及旧 mock 档保持原语义。
        if (action_type == "chat" and not allow_ai and not use_mock
                and not payload.get("whisper") and not payload.get("team")
                and isinstance(actor, str) and actor.startswith("player:")
                and not actor.startswith("player:ai:") and EngineDriver is not None):
            from server.player_input import parse_player_intent
            engine = self.get_engine(session)
            candidate = parse_player_intent(payload["text"], stage=session.get("stage"),
                                            locations=engine._loc_names)
            if candidate is not None:
                action_type, payload = candidate["action_type"], candidate["payload"]
        # rt 演出层分流（契约 §3.5c）：collect / bid_headline 由 AgentRuntime *_flow 承接
        if action_type == "skill" and \
                str((payload or {}).get("skill") or (payload or {}).get("kind") or "") in RT_SKILL_FLOWS and not (
                    not use_mock and str(payload.get("skill") or payload.get("kind")) in ("puzzle", "bid_headline")):
            async with self._action_lock_for(session_id):
                events, error = self._rt_skill_flow(session, actor, payload)
                if error is not None:
                    return [], {"status": 400, "notice": error}
                for evt in events:
                    session.setdefault("events", []).append(evt)
                session["actions"].append({"type": action_type, "actor": actor,
                                           "payload": payload or {}})
                self.store.save_session(session_id, session)
                if session.get("status") == "ended":
                    self._drop_action_lock(session_id)
            await self.broadcast(session_id, events)
            return await self._with_ai_wave(session_id, events, allow_ai)
        async with self._action_lock_for(session_id):
            try:
                if use_mock:
                    events, error = self.get_mock_engine(session).apply_action(
                        session, action_type, actor, payload, allow_ai=allow_ai)
                elif EngineDriver is None:
                    return [], {"status": 503,
                                "notice": "引擎适配层当前不可导入（engine/ 并发编辑中间态），"
                                          f"原因：{_ENGINE_IMPORT_ERROR}"}
                else:
                    events, error = self.get_engine(session).apply_action(
                        session, action_type, actor, payload, allow_ai=allow_ai)
            except Exception as e:  # 引擎异常如实上报，不伪造事件
                return [], {"status": 500,
                            "notice": f"引擎结算异常：{type(e).__name__}: {e}"}
            if error is not None:
                return [], {"status": 400, "notice": error}
            for evt in events:
                session.setdefault("events", []).append(evt)
            self.store.save_session(session_id, session)
            if session.get("status") == "ended":
                self._drop_action_lock(session_id)
        # rt 演出层（并存）：计数记账 → 终局成就/报告 → 轮转广播事故
        # 玩家聊天复用空席的配置解析：设置面板 / 环境变量 / 知乎默认通道。
        targeted_npc_chat = False
        if action_type == "chat" and not allow_ai and not use_mock:
            tgt = str(payload.get("target") or payload.get("char_id") or "dm").removeprefix("npc:")
            is_dm = tgt in ("dm", "kanshan", "dm_kanshan")
            if is_dm:
                tgt = "dm"
            targeted_npc_chat = not is_dm and bool(tgt)
            llm = self._llm_for_session(session_id)
            reply, failure = None, None
            provider = ""
            reply_kind = "llm"  # P1-2 诚实化：llm/identity_guarded/violations/fallback
            try:
                if llm is None or AgentRuntime is None:
                    failure = "AI 对话未配置可用接口，请检查 API 设置。"
                else:
                    rt = self.get_runtime(session)
                    eng = self.get_engine(session)
                    if is_dm:
                        from agents.llm_client import call_gateway
                        rt.dm.set_flaw_count(session.get("flaw_count", 0))
                        # to_thread（2026-09-14 P0-3 压测取证）：call_gateway 内部
                        # 是同步 urllib，直接在事件循环里调用会冻结全部 WS 心跳
                        # （10 并发时 8 连接 1011 被踢）。
                        reply = await asyncio.to_thread(
                            call_gateway, llm, rt.dm._persona_system(),
                            "请以主持人口吻简短回应玩家，只参考当前公开状态，不透露隐藏答案。\n"
                            + json.dumps({"stage": session.get("stage"),
                                          "actions_left": session.get("actions_left"),
                                          "player_text": payload.get("text", "")}, ensure_ascii=False),
                            provider="main")
                    elif tgt in rt.npcs:
                        dv = eng.ms.current_version(tgt)
                        while rt.memory.current_version(tgt) < dv:
                            rt.memory.unlock_next(tgt, "memory_fix")
                        npc = rt.npcs[tgt]
                        previous = npc.gateway
                        npc.gateway = llm
                        try:
                            # npc_chat 为纯同步函数（LLM urllib + 守卫），to_thread
                            # 化保证事件循环在 LLM 往返期间持续服务其他连接。
                            npc_res = await asyncio.to_thread(
                                rt.npc_chat, tgt, payload.get("text", ""))
                            reply = npc_res.get("reply")
                            reply_kind = npc_res.get("reply_kind") or "llm"
                        finally:
                            npc.gateway = previous
                    else:
                        failure = "请选择一位在场角色再对话。"
                    provider = getattr(llm, "last_provider", "")
                    # LLM 层失败（last_error/mock/fallback）才重试；守卫层替换
                    # （identity_guarded/violations）已有兜底台词，重试无意义。
                    llm_failed = (bool(getattr(llm, "last_error", ""))
                                  or provider in ("mock", "fallback"))
                    if llm_failed:
                        # 瞬时限流（429 退避后仍失败）：2.5s 后静默重试一次，玩家无感
                        await asyncio.sleep(2.5)
                        try:
                            if is_dm:
                                reply = await asyncio.to_thread(
                                    call_gateway, llm, rt.dm._persona_system(),
                                    "请以主持人口吻简短回应玩家，只参考当前公开状态，不透露隐藏答案。\n"
                                    + json.dumps({"stage": session.get("stage"),
                                                  "actions_left": session.get("actions_left"),
                                                  "player_text": payload.get("text", "")}, ensure_ascii=False),
                                    provider="main")
                            elif tgt in rt.npcs:
                                npc = rt.npcs[tgt]
                                previous = npc.gateway
                                npc.gateway = llm
                                try:
                                    npc_res = await asyncio.to_thread(
                                        rt.npc_chat, tgt, payload.get("text", ""))
                                    reply = npc_res.get("reply")
                                    reply_kind = npc_res.get("reply_kind") or "llm"
                                finally:
                                    npc.gateway = previous
                            provider = getattr(llm, "last_provider", "")
                            llm_failed = (bool(getattr(llm, "last_error", ""))
                                          or provider in ("mock", "fallback"))
                        except Exception:
                            pass
                    if llm_failed:
                        why = (llm.degrade_log[-1] if getattr(llm, "degrade_log", None)
                               else "") or "上游暂不可用"
                        failure = (f"AI 接口暂时未能返回回复（{why[:90]}）。"
                                   "多为知乎直答限流，等 10 秒再试即可。")
                    elif not reply:
                        failure = failure or "AI 未返回有效回复，请重试。"
            except Exception:
                failure = "AI 对话生成失败，请稍后重试或检查 API 配置。"
            # 身份净化（2026-09-14 实跑取证：zhida 会自曝「我是知乎直答」）：
            # 先按同一路径重试一次（成本 ≤1 次调用），仍命中则换预写台词。
            # 绝不把产品介绍/身份说明发给玩家；provider 保持真实来源不伪装。
            identity_guarded = False
            if not failure and reply and has_product_identity(str(reply)):
                identity_guarded = True
                retry_reply = None
                try:
                    from agents.llm_client import call_gateway
                    if is_dm:
                        retry_reply = await asyncio.to_thread(
                            call_gateway, llm, rt.dm._persona_system(),
                            "请以主持人口吻简短回应玩家，只参考当前公开状态，不透露隐藏答案。\n"
                            + json.dumps({"stage": session.get("stage"),
                                          "actions_left": session.get("actions_left"),
                                          "player_text": payload.get("text", "")},
                                         ensure_ascii=False) + "\n" + RETRY_HINT,
                            provider="zhida")
                    elif tgt in rt.npcs:
                        npc = rt.npcs[tgt]
                        previous = npc.gateway
                        npc.gateway = llm
                        try:
                            retry_reply = (await asyncio.to_thread(
                                rt.npc_chat, tgt, payload.get("text", ""))).get("reply")
                        finally:
                            npc.gateway = previous
                except Exception:
                    retry_reply = None
                if retry_reply and not has_product_identity(str(retry_reply)):
                    reply = retry_reply
                else:
                    from agents.llm_client import fallback_text
                    reply = fallback_text("stage_announce" if is_dm else "npc_reply")
                    reply_kind = "identity_guarded"
            # 替换引擎占位，同时持久化最终回复，重连后仍能看到。
            pending = [e for e in events if e.get("type") == "system"
                       and e.get("payload", {}).get("event") == "npc_pending"]
            events = [e for e in events if e not in pending]
            if failure:
                reply_event = make_event("system", session_id, session["round"], "dm", {
                    "event": "ai_reply_failed", "notice": failure, "toast": failure,
                    "kind": "warn", "reply_to": actor, "target": tgt})
            else:
                # P1-2 诚实化：守卫层替换（identity_guarded/violations）时
                # provider 标 fallback:* 并带 degraded，前端/诊断可识别降级。
                if reply_kind != "llm":
                    provider = f"fallback:{reply_kind}"
                reply_event = make_event("chat", session_id, session["round"],
                    "dm" if is_dm else "npc:" + tgt, {
                        "text": str(reply), "source": "agent", "provider": provider,
                        "ai_provider": str(provider or ""),
                        "degraded": reply_kind != "llm",
                        "identity_guarded": identity_guarded,
                        "actor_kind": "dm" if is_dm else "npc", "char_id": tgt,
                        "target": tgt, "reply_to": actor})
            events.append(reply_event)
            async with self._action_lock_for(session_id):
                session = self.store.load_session(session_id) or session
                session["events"] = [e for e in session.get("events", []) if e not in pending]
                session["events"].append(reply_event)
                self.store.save_session(session_id, session)
        rt = self.get_runtime(session) if AgentRuntime is not None else None
        rt_events: list[dict] = []
        if rt is not None:
            for evt in events:
                self._feed_rt_event(rt, evt)
            ending_evt = next((e for e in events if e["type"] == "ending"), None)
            if ending_evt is not None:
                rt_events.extend(self._rt_ending_flow(session, ending_evt))
            elif any(e["type"] == "system"
                     and e["payload"].get("event") == "stage_changed"
                     for e in events):
                try:
                    from engine.booklet import stage_to_chapter
                    rt.sync_booklets(stage_to_chapter(session.get("stage")))
                except Exception:
                    pass
                if random.random() < 0.3:
                    rt_events.extend(self._rt_broadcast_accident(session))
        if rt_events:
            async with self._action_lock_for(session_id):
                session = self.store.load_session(session_id) or session
                for evt in rt_events:
                    session.setdefault("events", []).append(evt)
                self.store.save_session(session_id, session)
            events = events + rt_events
        await self.broadcast(session_id, events)
        # P0-2：定向 NPC 私聊不触发自走棋 wave（npc_chat 已直接回应玩家；
        # wave 的 9 席串行 LLM 会持锁 60s+ 压死同房间后续消息）。
        if targeted_npc_chat:
            return events, None
        return await self._with_ai_wave(session_id, events, allow_ai)

    async def _with_ai_wave(self, session_id: str, events: list[dict],
                            allow_ai: bool) -> tuple[list[dict], None]:
        """真人动作后补空席 AI；allow_ai=True（run_ai_act 内部）不再 wave，防递归。

        真人「公开聊天」走社交回应路径（AI 针对聊天内容回答/追问/质疑，
        并跟随 DM 引导轮流介绍/陈述证词）；其余动作（搜证/技能/投票）保持
        自走棋 wave（PlayerAgent 按闭卷决策）。

        P0-3 终版（2026-09-14 压测取证）：wave 改为后台任务（fire-and-forget）
        ——此前在本协程内 await 全席串行 LLM（60s~2min），把同连接/同房间
        后续消息全部压死（含 ping），是「AI 聊不起来」的最终元凶。后台任务
        自行落库 + 广播；_ai_waving 防重入；任务引用存 _last_wave_task 供测试。
        """
        if allow_ai or getattr(self, "_ai_waving", False):
            if getattr(self, "_ai_waving", False) and not allow_ai:
                # P0-3 终版（压测取证）：wave 进行中不丢弃新意图——排入
                # pending，由后台任务消化。否则最后一个动作的 AI 补位丢失
                # （solo 投票阶段 needed 永远无法满足，对局死锁）。
                self._wave_pending = True
                self._wave_pending_social = any(
                    e.get("type") == "chat"
                    and str((e.get("payload") or {}).get("target") or "").removeprefix("npc:") in ("", "dm")
                    for e in events)
            return events, None
        # 定向对具体 NPC 的真人私聊（2026-09-14 P0-2 压测取证）：定向回应由
        # 引擎内 npc_pending→npc_chat 链路完成，不再触发任何 wave。
        if any(
                e.get("type") == "chat"
                and str((e.get("payload") or {}).get("target") or "").removeprefix("npc:") not in ("", "dm")
                and str(e.get("actor") or "").startswith("player:")
                and not str(e.get("actor") or "").startswith("player:ai:")
                and not (e.get("payload") or {}).get("whisper")
                for e in events):
            return events, None
        # 全场广播式发言（无 target 或对 DM）才触发社交回应；其余动作走
        # 自走棋 wave。引擎会把 target 规范化为 npc: 前缀，统一剥离后比较。
        has_human_broadcast_chat = any(
            e.get("type") == "chat"
            and not (e.get("payload") or {}).get("whisper")
            and not (e.get("payload") or {}).get("team")
            and str((e.get("payload") or {}).get("target") or "").removeprefix("npc:") in ("", "dm")
            and str(e.get("actor") or "").startswith("player:")
            and not str(e.get("actor") or "").startswith("player:ai:")
            for e in events)
        self._last_wave_task = asyncio.create_task(
            self._run_wave_background(session_id, has_human_broadcast_chat))
        return events, None

    async def _run_wave_background(self, session_id: str,
                                   use_social: bool) -> None:
        """后台跑 wave：不阻塞任何玩家动作。

        广播与落库由子路径自治（契约 2026-09-14 双广播修复 + npc_social 逐席
        实时广播）：run_ai_wave 每席 run_action(allow_ai=True) 内部落库并广播；
        run_chat_respond（npc_social）逐席广播 + save_session。本函数若再
        广播/落库即为双份（message_id 重复事故，回归守护 test_chat_dup_guard）。
        wave 进行中到达的新意图进 _wave_pending 队列，本任务循环消化——
        保证最后一拍动作的 AI 补位不丢（否则投票阶段死锁）。
        """
        self._ai_waving = True
        try:
            pending_social = use_social
            while True:
                try:
                    if pending_social:
                        await self.run_chat_respond(session_id)
                    else:
                        await self.run_ai_wave(session_id)
                except Exception:
                    pass  # 后台 wave 失败不传播：玩家动作已完成，降级在事件内可见
                if getattr(self, "_wave_pending", False):
                    pending_social = bool(getattr(self, "_wave_pending_social", False))
                    self._wave_pending = False
                    continue
                break
        finally:
            self._ai_waving = False

    async def run_chat_respond(self, session_id: str) -> list[dict]:
        """真人公开发言后的 AI 社交回应：走 npc_social 公开波（带最近聊天
        上下文 + DM 引导 phase 推断）。LLM 未配置或全部失败时回退自走棋
        wave，保持旧行为，零副作用。"""
        if self.store is None:
            return []
        session = self.store.load_session(session_id)
        if session is None or session.get("status") != "playing":
            return []
        if session.get("engine", "mock") == "mock" or self._llm_for_session(session_id) is None:
            return await self.run_ai_wave(session_id)
        sender = "player:1"
        for ev in reversed(session.get("events") or []):
            if ev.get("type") != "chat":
                continue
            actor0 = str(ev.get("actor") or "")
            if actor0.startswith("player:") and not actor0.startswith("player:ai:"):
                sender = actor0
                break
        body = {"player_id": sender, "prompt": "", "respond_trigger": True}
        try:
            from .npc_social import social_request
            res = await social_request(self, session_id, body, private=False)
            return list(res.get("events") or [])
        except Exception:
            return await self.run_ai_wave(session_id)

    async def run_ai_wave(self, session_id: str) -> list[dict]:
        """空席整桌各行动一步；前端对其中的 AI 台词做轮流播报。"""
        from .booklet_svc import take_wave_roles
        if self.store is None:
            return []
        session = self.store.load_session(session_id)
        if session is None or session.get("status") != "playing":
            return []
        roles = take_wave_roles(session)
        self.store.save_session(session_id, session)
        collected: list[dict] = []
        for role in roles:
            session = self.store.load_session(session_id)
            if session is None or session.get("status") != "playing": break
            try:
                preview, err = await self.run_ai_act(session_id, role, dry_run=True)
                pre_decision = (preview or {}).get("decision") or {}
                if err is not None:
                    collected.append(await self._emit_ai_act_failed(session_id, role, err))
                    continue
                if pre_decision.get("type") == "advance":
                    continue
                body, err = await self.run_ai_act(
                    session_id, role, dry_run=False,
                    prefetched_decision=pre_decision)
                if err is not None:
                    collected.append(await self._emit_ai_act_failed(session_id, role, err))
                    continue
                if body.get("applied"):
                    seat_events = body.get("events") or []
                    collected.extend(seat_events)
                    # 广播契约（2026-09-14 双广播修复）：本批事件已由
                    # run_ai_act → run_action(allow_ai=True) 内部统一广播
                    # （run_action 末尾 broadcast），此处不得再广播同一批
                    # seat_events——曾因双广播 + 事件无 message_id 导致
                    # WS 前端每条 AI 台词相邻上屏两遍。非 WS 前端走
                    # HTTP /ai_wave 响应的 events，保持不变。
            except Exception as exc:
                collected.append(await self._emit_ai_act_failed(
                    session_id, role,
                    {"status": 500, "notice": f"AI 行动异常：{type(exc).__name__}: {exc}"}))
        # AI 演出位：小游戏（心声窃听）+ 暗拍/头条，每幕各至多一次，零副作用兜底
        try:
            collected.extend(self._ai_showtime_spot(session_id, roles))
        except Exception:
            pass
        return collected

    @staticmethod
    def _ai_act_failed_event(session_id: str, role: str, error: dict) -> dict:
        """Make AI-seat failures visible without faking a successful action."""
        return make_event("system", session_id, 0, f"player:ai:{role}", {
            "event": "ai_act_failed",
            "role_id": role,
            "status": int((error or {}).get("status") or 500),
            "notice": str((error or {}).get("notice") or "AI 席行动失败"),
            "source": "server",
        })

    async def _emit_ai_act_failed(self, session_id: str, role: str, error: dict) -> dict:
        event = self._ai_act_failed_event(session_id, role, error)
        if self.store is not None:
            session = self.store.load_session(session_id)
            if session is not None:
                session.setdefault("events", []).append(event)
                self.store.save_session(session_id, session)
        await self.broadcast(session_id, [event])
        return event

    def _ai_showtime_spot(self, session_id: str, roles: list[str]) -> list[dict]:
        """AI 坐席的"像真人一样玩"演出位：每幕每类至多一次，确定性作答/投标，
        判定与结算仍归 bridge/引擎（只演不裁）。失败静默跳过，不影响对局。"""
        session = self.store.load_session(session_id)
        if session is None or session.get("status") != "playing" or not roles:
            return []
        stage = str(session.get("stage") or "")
        rnd = int(session.get("round") or 1)
        marker = f"ai_show_{stage}_{rnd}"
        played = set(session.get("ai_show_played") or [])
        if marker in played:
            return []
        rt = self.get_runtime(session)
        if rt is None:
            return []
        actor = f"ai:{roles[0]}"
        events: list[dict] = []

        def _emit(event: str, text: str, **extra):
            payload = {"event": event, "text": text, "source": "engine",
                       "actor": actor, **extra}
            events.append(make_event("system", session_id, rnd, "dm", payload))

        # 1) 小游戏位：心声窃听器（答对答错都如实结算——AI 也会失手）
        if stage in ("investigate", "round_table"):
            try:
                pool = rt.memory_puzzle_pool("open")
                if pool:
                    item = pool[rnd % len(pool)]
                    pick = "A" if (hash(session_id) + rnd) % 2 == 0 else "B"
                    res = rt.heart_quiz_flow(item, pick)
                    _emit("minis_ai_play",
                          f"叮——{item.get('npc', '神秘人')} 在玩「心声窃听器」："
                          + ("答对了，热身关通过。" if res.get("correct")
                             else "答错了。弹幕已经就位，不扣进度。"),
                          game="heart_quiz", pick=pick,
                          correct=bool(res.get("correct")),
                          npc=item.get("npc", ""), show=str(res.get("show") or ""))
            except Exception as exc:
                _emit("minis_ai_play", f"叮——小游戏位本轮跳过（{type(exc).__name__}）。")
        # 2) 演出位：第二幕 AI 暗拍 / 第三幕 AI 头条竞标（actor 参数化后 AI 可执行）
        if stage == "investigate":
            try:
                res: dict = {}
                for loc, kw in (("茶水间", "时间线"), ("监控室", "日志"),
                                ("档案室", "封条")):
                    res = rt.stealth_photo_flow(loc, kw, actor=actor)
                    if res.get("ok"):
                        _emit("ai_stealth_photo",
                              f"叮——{roles[0]} 趁人不备在{loc}暗拍了一张「{kw}」照片"
                              f"（线索留在原地，暗房大师素材 +1）。", ok=True)
                        break
                if not res.get("ok"):
                    _emit("ai_stealth_photo",
                          f"叮——{roles[0]} 想暗拍但快门全被值班 camera 记了正着，作罢。",
                          ok=False,
                          notice=str(res.get("env_note")
                                     or res.get("reason")
                                     or res.get("notice") or ""))
            except Exception as exc:
                _emit("ai_stealth_photo",
                      f"叮——暗拍位本轮跳过（{type(exc).__name__}）。", ok=False)
        elif stage == "round_table":
            try:
                res = rt.headline_flow(actor, "swayable", 1,
                                       topic=f"#{rnd} 号位AI竞标#")
                line = str(res.get("result_line")
                           or res.get("host_line") or "头条竞标完成")
                _emit("ai_headline_bid", f"叮——{roles[0]} 参与了头条竞标：{line}",
                      settle=bool((res.get("settle") or {}).get("ok")))
            except Exception:
                pass
        if events:
            played.add(marker)
            session["ai_show_played"] = sorted(played)
            session.setdefault("events", []).extend(events)  # 落事件流：REST 拉取也可回看
            self.store.save_session(session_id, session)
        return events

    async def run_ai_act(self, session_id: str, char_id: str,
                         dry_run: bool = False,
                         prefetched_decision: dict | None = None
                         ) -> tuple[dict, dict | None]:
        """按该角色已开封的闭卷提议并（可选）执行一步。

        prefetched_decision：预检（dry_run）阶段已拿到的决策——直接复用，
        省掉执行阶段的第二次 LLM 调用（知乎直答有 QPS 限流，AI 波减半）。"""
        session = self.store.load_session(session_id)
        if session is None:
            return {}, {"status": 404, "notice": f"对局不存在：{session_id}"}
        from agents.player_agent import PlayerAgent
        from .booklet_svc import (chapter_of, legal_actions, library_of,
                                  other_chars)

        lib = library_of(session)
        role = lib.resolve_role(char_id, solo=session.get("mode") != "party")
        if role not in lib.roles:
            return {}, {"status": 400, "notice": f"没有这本闭卷：{char_id}"}
        stage = session.get("stage") or "break_ice"
        allowed = legal_actions(session)
        ticks = session.setdefault("ai_seat_ticks", {})
        # 持久化每个 AI 席位的可解释状态，供下一轮决策和前端诊断使用。
        ai_state = session.setdefault("ai_state", {}).setdefault(role, {
            "known_clues": [], "suspects": {}, "trust": 20,
            "goal": "搜集线索并完成阵营任务", "last_action": ""
        })
        host = next((p.get("player_id") for p in session.get("players") or []
                     if str(p.get("player_id") or "").startswith("player:")
                     and "ai:" not in str(p.get("player_id"))), "player:1")
        last_human = ""
        for ev in reversed(session.get("events") or []):
            if ev.get("type") != "chat":
                continue
            actor0 = str(ev.get("actor") or "")
            if actor0.startswith("ai:") or actor0.startswith("player:ai:"):
                continue
            if actor0.startswith("player:"):
                last_human = str((ev.get("payload") or {}).get("text") or "")
                break
        state = {
            "other_chars": other_chars(session, role),
            "ap": session.get("actions_left"),
            "held_clues": list(session.get("clues_gained") or []),
            "held_cards": list(session.get("held_cards") or []),
            "evidence": list(session.get("evidence_cards") or []),
            "open_skills": list(session.get("open_skills") or []),
            "seat_tick": int(ticks.get(role) or 0),
            "host_id": host,
            "last_human_text": last_human,
            "ai_memory": {
                "known_clues": list(ai_state.get("known_clues", [])),
                "suspects": dict(ai_state.get("suspects", {})),
                "trust": int(ai_state.get("trust", 20)),
                "goal": ai_state.get("goal", "搜集线索并完成阵营任务"),
            },
        }
        gateway = self._llm_for_session(session_id)
        agent = PlayerAgent(lib, gateway)
        decision_started = time.perf_counter()
        # decide 内部为同步 LLM 调用（LLM_TIMEOUT=30s + 429 退避最多 ~24s），
        # 必须放线程池执行，否则阻塞事件循环冻结全服务心跳（与 npc_social 同法）。
        # 预检（dry_run）已拿到的决策直接复用：AI 波每省一次 LLM 调用（限流减负）。
        if prefetched_decision:
            decision = dict(prefetched_decision)
            decision["meta"] = {"prefetched": True}
        else:
            decision = await asyncio.to_thread(agent.decide, role, stage=stage,
                                               legal=allowed, state=state,
                                               use_llm=gateway is not None)
            decision["meta"] = {
                "legal": list(allowed),
                "provider": getattr(gateway, "last_provider", "heuristic") if gateway else "heuristic",
                "latency_ms": round((time.perf_counter() - decision_started) * 1000, 1),
            }
        act_type = str(decision.get("type") or "chat")
        payload = dict(decision.get("payload") or {})
        # 身份净化：AI 席位台词直接进公共频道，命中产品自曝即换预写台词
        # （此处不重试：整桌 wave 会放大调用成本；命中标记便于诊断）。
        if has_product_identity(payload.get("text")):
            from agents.llm_client import fallback_text
            payload["text"] = fallback_text("npc_reply")
            payload["identity_guarded"] = True
            decision["payload"] = payload
            decision.setdefault("meta", {})["identity_guarded"] = True
        if act_type in ("private_chat", "whisper", "introduce", "reveal_clue"):
            if act_type in ("private_chat", "whisper") and host:
                payload["whisper"] = True
                payload.setdefault("to", host)
                payload.setdefault("text", payload.get("text") or "这句只给你。")
            act_type = "chat"
            decision["type"] = "chat"
            decision["payload"] = payload
        body = {
            "ok": True,
            "role_id": role,
            "chapter": chapter_of(session),
            "stage": stage,
            "decision": decision,
            "applied": False,
            "events": [],
        }
        if dry_run:
            return body, None
        actor = (f"ai:{role}" if session.get("mode") == "party"
                 else f"player:ai:{role}")
        events, error = await self.run_action(
            session_id, act_type, actor, payload,
            allow_ai=True)
        if error is not None and actor.startswith("ai:"):
            events, error = await self.run_action(
                session_id, act_type, f"player:ai:{role}",
                payload, allow_ai=True)
        if error is not None:
            return body, error
        session = self.store.load_session(session_id) or session
        ticks = session.setdefault("ai_seat_ticks", {})
        ticks[role] = int(ticks.get(role) or 0) + 1
        ai_state["last_action"] = act_type
        # 只从服务端已裁决事件提取线索，AI 自己不能创造事实。
        for evt in events:
            ep = evt.get("payload") or {}
            clue = ep.get("clue_id") or ep.get("card_id")
            if clue and clue not in ai_state["known_clues"]:
                ai_state["known_clues"].append(str(clue))
        target = str(payload.get("target") or payload.get("char_id") or "")
        if target and target != role and act_type in ("chat", "vote", "accuse"):
            suspects = ai_state.setdefault("suspects", {})
            suspects[target] = min(100, int(suspects.get(target, 0)) + 5)
        self.store.save_session(session_id, session)
        for e in events:
            (e.setdefault("payload", {}))["booklet_act"] = True
            e["payload"]["booklet_role"] = role
            e["payload"]["booklet_reason"] = decision.get("reason")
        body["applied"] = True
        body["events"] = events
        body["actor"] = actor
        return body, None

    # ------------------------------------------------------------- WS 消息
    async def handle(self, ws, raw: str):
        """路由 WS 客户端消息（签名保持）。

        支持文本 "ping" → system/pong；JSON 事件 type ∈ CLIENT_ACTIONS → 动作管线。
        违反契约 §3.6 的类型直接回 system 错误事件（真实原因，不静默丢弃）。
        """
        session_id = getattr(ws.state, "room_id", None)
        if session_id is None:
            return
        if raw.strip() == "ping":
            pong = make_event("system", session_id, 0, "kanshan",
                              {"event": "pong", "server_time": time.time(),
                               "mock": mock_enabled()})
            await ws.send_text(json.dumps(pong, ensure_ascii=False))
            return
        try:
            msg = json.loads(raw)
        except ValueError:
            await self._send_error(ws, session_id, "消息不是合法 JSON")
            return
        if not isinstance(msg, dict):
            await self._send_error(ws, session_id, "消息必须是 JSON 对象")
            return
        action_type = str(msg.get("type", ""))
        raw_payload = msg.get("payload")
        if action_type == "skill" and isinstance(raw_payload, dict) and raw_payload.get("skill") == "memory_read":
            session = self.store.load_session(session_id)
            pid = getattr(ws.state, "player_id", None)
            connected = self.rooms.get(session_id, {}).get("players", {}).get(pid)
            if (not session or connected is not ws or getattr(ws.state, "spectator", False)
                    or pid not in {p.get("player_id") for p in session.get("players", [])}):
                await self._send_error(ws, session_id, "请先以玩家身份连接房间")
                return
            cid = str(raw_payload.get("target", "")).removeprefix("npc:")
            if cid not in {n["id"] for n in session.get("npcs", [])}:
                await self._send_error(ws, session_id, "角色不存在")
                return
            payload = self.get_engine(session).memory_view(cid)
            payload.update(event="memory_snapshot", source="engine")
            await ws.send_text(json.dumps(make_event("system", session_id,
                session.get("round", 1), "dm", payload), ensure_ascii=False))
            return
        if action_type not in CLIENT_ACTIONS:
            await self._send_error(
                ws, session_id,
                f"未支持的客户端事件类型：{action_type or '(空)'}"
                f"（契约 §3.6 仅限 {'/'.join(CLIENT_ACTIONS)}）")
            return
        # WS 入口内容安全检查（中间件不覆盖 WS 消息）
        payload = msg.get("payload") or {}
        texts = [payload.get("text"), payload.get("target"),
                 payload.get("card"), payload.get("skill")]
        for t in texts:
            ok, reason = check_text(str(t)) if t else (True, None)
            if not ok:
                await self._send_error(
                    ws, session_id,
                    f"内容安全过滤：检测到{reason}，消息已拦截（未消耗任何额度）")
                return
        actor = str(msg.get("actor", "player:1"))
        # 真实玩家公开聊天的引擎动作已在 run_action 前段确定性落库，
        # 后续 LLM 回复可能等待限流/重试；后台化避免同一 WS 的下一条
        # advance/search 被聊天回复阻塞。定向私聊、AI 动作和 mock 保持原语义。
        session = self.store.load_session(session_id)
        use_mock = bool(session and session.get("engine", "mock") == "mock")
        public_player_chat = (
            action_type == "chat" and not use_mock
            and not payload.get("whisper") and not payload.get("team")
            and actor.startswith("player:") and not actor.startswith("player:ai:"))
        if public_player_chat:
            self._spawn_ws_action(ws, session_id, action_type, actor, payload)
            return
        events, error = await self.run_action(session_id, action_type, actor, payload)
        if error is not None:
            await self._send_error(ws, session_id, error["notice"])

    async def _send_error(self, ws, session_id: str, notice: str):
        evt = make_event("system", session_id, 0, "kanshan",
                         {"event": "error", "notice": notice})
        try:
            await ws.send_text(json.dumps(evt, ensure_ascii=False))
        except Exception:
            pass


# ------------------------------------------------------------------ 应用装配
game_server = GameServer(SCENARIO_DIR)
voice_hub = VoiceHub()  # 独立信令；不写 store / 不碰 PartyBoard / 不进引擎


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = SessionStore(DATA_DIR)
        app.state.gateway = ZhihuGateway(
            app_id="", app_key="", cache_dir=DATA_DIR / "cache")
        app.state.oauth = ZhihuOAuth()
        app.state.engine = MockStateMachine(SCENARIO_DIR, app.state.store)
        app.state.engine_available = False
        app.state.engine_error = _ENGINE_IMPORT_ERROR
        if engine_mode() == "engine":
            if EngineDriver is None:
                pass  # 引擎适配层导入失败：错误已在 _ENGINE_IMPORT_ERROR
            else:
                try:
                    EngineDriver(SCENARIO_DIR)  # 启动时验证引擎+内容可装载
                    app.state.engine_available = True
                    app.state.engine_error = None
                except Exception as e:  # 引擎/内容不可装载 → 如实降级并标注
                    app.state.engine_error = f"{type(e).__name__}: {e}"
        game_server.store = app.state.store
        game_server.gateway = app.state.gateway
        game_server.oauth = app.state.oauth
        game_server.engine = app.state.engine
        # minis 数据源（C 组口径）：rt.memory_puzzle_pool(tier) / rt.heart_quiz_flow。
        # 免登录路径无需 session、零额度；独立 minis rt（不进对局 runtime 缓存）。
        minis_rt = None
        if AgentRuntime is not None:
            try:
                minis_rt = AgentRuntime(SCENARIO_DIR, session_id="minis")
            except Exception as _e:
                print(f"[minis] AgentRuntime 装载失败：{type(_e).__name__}: {_e}",
                      flush=True)
        app.state.minis_rt = minis_rt
        app.state.started_at = time.time()
        voice_hub.reset()
        app.state.voice_hub = voice_hub
        yield
        await app.state.gateway.close()

    app = FastAPI(title="求真档案局·看山失踪夜 — Server",
                  version="0.2.0-f-window", lifespan=lifespan)

    app.add_middleware(ContentSafetyMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"])
    # /assets/* 静态托管（契约 v2.1 §3.7）：前端所有图片/视频从此取，禁止外链
    assets_dir = GAME_ROOT / "content" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    # 前端静态托管（M4 部署：单端口同时服务 API + 前端）
    frontend_dir = GAME_ROOT / "frontend"
    app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")
    app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
    # 小游戏层：index.html 以相对路径 `minis/*.js` 加载（解析为 /minis/*.js），
    # 此前只挂了 /js 与 /css，导致 4 件套 + main-minis 在部署环境全部 404。
    _minis_dir = frontend_dir / "minis"
    _minis_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/minis", StaticFiles(directory=str(_minis_dir)), name="minis")

    @app.get("/", include_in_schema=False)
    async def index():
        from fastapi.responses import FileResponse
        return FileResponse(frontend_dir / "index.html")
    return app


app = create_app()


def _require(state_attr: str):
    v = getattr(app.state, state_attr, None)
    if v is None:
        raise HTTPException(status_code=503, detail="服务正在初始化，请稍后重试")
    return v


_LLM_HDRS = (("X-LLM-BASE", "llm_base"), ("X-LLM-KEY", "llm_key"),
             ("X-LLM-MODEL", "llm_model"), ("X-ZHIHU-SECRET", "zhihu_secret"))


def ingest_api_headers(req: Request, session_id: str | None = None) -> dict:
    """从请求头吃进会话级 LLM 配置（只进内存，不落盘）。"""
    api_cfg = {}
    for hkey, cfgkey in _LLM_HDRS:
        v = req.headers.get(hkey)
        if v:
            api_cfg[cfgkey] = v
    if api_cfg and session_id:
        app.state.api_cfg = getattr(app.state, "api_cfg", {})
        cur = dict(app.state.api_cfg.get(session_id) or {})
        cur.update(api_cfg)
        app.state.api_cfg[session_id] = cur
    return api_cfg


def _slim_job_for_response(job: dict) -> dict:
    """生成轮询响应：统一任务/剧本编号并去掉 detail.memories 全文。"""
    out = dict(job)
    scenario_id = str(out.get("scenario_id") or out.get("id") or "")
    if scenario_id:
        out["scenario_id"] = scenario_id
        out.setdefault("job_id", scenario_id)
    detail = dict(out.get("detail") or {})
    detail.pop("memories", None)
    out["detail"] = detail
    return out


def _seat_char_id(session: dict, player_id: str, welcome: dict | None = None) -> str:
    """从 welcome.seat / seats_public / seats 取该请求玩家已入座的 char_id。"""
    if isinstance(welcome, dict):
        seat = (welcome.get("payload") or {}).get("seat")
        if isinstance(seat, dict) and seat.get("char_id"):
            return str(seat["char_id"])
    pid = str(player_id or "")
    for s in list(session.get("seats_public") or []) + list(session.get("seats") or []):
        if isinstance(s, dict) and s.get("player_id") == pid and s.get("char_id"):
            return str(s["char_id"])
    return ""


_PUBLIC_STRIP_KEYS = ("faction", "winner_faction", "guilt", "inner_truth")


def public_session_view(session: dict | None) -> dict:
    """HTTP/WS 对局视图：暗置阵营与里层真相不得出现在响应里。

    落盘 session 仍可保留内部字段；本函数返回深拷贝。
    """
    if not session:
        return {}
    view = copy.deepcopy(session)
    view.pop("party", None)
    view.pop("player_book", None)
    view.pop("ai_state", None)  # 隐藏目标和怀疑度不发送给玩家
    view.pop("npc_private_memory", None)
    view["events"] = [e for e in view.get("events", [])
                      if not (e.get("payload") or {}).get("whisper")]

    def _strip_row(row):
        if not isinstance(row, dict):
            return row
        return {k: v for k, v in row.items() if k not in _PUBLIC_STRIP_KEYS}

    view["players"] = [_strip_row(p) for p in view.get("players") or []]
    view["npcs"] = [_strip_row(n) for n in view.get("npcs") or []]
    try:
        from .booklet_svc import public_booklet_view
    except Exception:
        public_booklet_view = None
    if public_booklet_view:
        for evt in view.get("events") or []:
            if not isinstance(evt, dict):
                continue
            payload = evt.get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("booklet"), dict):
                payload["booklet"] = public_booklet_view(payload["booklet"])
    return view


def _http_player_book(scenario_id: str | None, char_id: str | None):
    """仅供 HTTP 响应：gen_* 且有本则返回全本，否则 None（不抛、不写事件）。"""
    sid = str(scenario_id or "").strip()
    cid = str(char_id or "").strip()
    if not sid.startswith("gen_") or not cid or load_player_book is None:
        return None
    try:
        return load_player_book(sid, cid)
    except FileNotFoundError:
        return None
    except Exception:
        return None


# ------------------------------------------------------------------ §3.7 路由
# ------------------------------------------------------ Studio 工作台（只增）
def _require_studio():
    if generate is None:
        raise HTTPException(status_code=503, detail=(
            "工作台模块不可用（studio/ 装载失败）："
            f"{_STUDIO_IMPORT_ERROR or 'unknown'}"))


# 创作任务进程内存表（job_id → 进度记录）+ 创作互斥锁：
# 同一时刻只放行一个 generate 任务，避免与对局抢 LLM 并发。
_STUDIO_JOBS: dict[str, dict] = {}
_STUDIO_GEN_LOCK = asyncio.Lock()


@app.post("/api/studio/generate")
async def studio_generate(req: Request):
    """一句话生成快本（异步受理：202 → 轮询 GET /api/studio/jobs/{job_id}）。"""
    _require_studio()
    try:
        body = await req.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    brief = body.get("brief") if isinstance(body.get("brief"), dict) else None
    seed = str(body.get("seed", "")).strip()
    if not seed and brief:
        seed = str(brief.get("hook") or "").strip()
    if not seed:
        raise HTTPException(status_code=400, detail="seed 不能为空")
    tier = str(body.get("tier", "demo"))
    try:
        from studio.tiers import TIERS as _studio_tiers
    except Exception:
        _studio_tiers = ()
    if _studio_tiers and tier not in _studio_tiers:
        raise HTTPException(status_code=400, detail=(
            f"tier 必须为 {'/'.join(_studio_tiers)}，收到：{tier!r}"))
    use_llm = bool(body.get("use_llm", False))
    inner_boss = bool(body.get("inner_boss", False))
    # zhihu 素材桥参数：本版本只校验透传（占位写入 job.zhihu_refs），不实际调用——
    # 素材桥由并行开发接入后在此消费。
    zhihu = body.get("zhihu") if isinstance(body.get("zhihu"), dict) else None
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    rec: dict = {"job_id": job_id, "status": "running", "seed_text": seed,
                 "tier": tier, "scenario_id": None,
                 "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _STUDIO_JOBS[job_id] = rec

    def _run() -> None:
        try:
            job = generate(seed, tier=tier, use_llm=use_llm,
                           inner_boss=inner_boss, brief=brief)
        except Exception as e:  # noqa: BLE001 —— 失败落进内存记录供轮询
            rec["status"] = "failed"
            rec["error"] = f"{type(e).__name__}: {e}"
            return
        job["job_id"] = job_id
        job["zhihu_refs"] = zhihu or {}
        rec.update(_slim_job_for_response(job))
        # 任务受理时 scenario_id 尚未知；终态必须回填实际可玩的 gen_*。
        rec["scenario_id"] = job.get("id")

    async def _runner() -> None:
        async with _STUDIO_GEN_LOCK:
            await asyncio.to_thread(_run)

    asyncio.create_task(_runner())
    return JSONResponse(status_code=202, content={
        "ok": True, "job_id": job_id, "scenario_id": rec["scenario_id"],
        "status": "running",
        "notice": f"生成任务已受理，请轮询 GET /api/studio/jobs/{job_id}"})


@app.get("/api/studio/jobs/{job_id}")
async def studio_job(job_id: str):
    """创作任务进度（内存优先；job_id 兼容直接查 gen_* scenario_id 的磁盘 job）。"""
    _require_studio()
    rec = _STUDIO_JOBS.get(job_id)
    if rec is not None:
        return {"ok": True, "job": rec}
    if str(job_id).startswith("gen_"):
        try:
            return {"ok": True, "job": _slim_job_for_response(load_job(job_id))}
        except FileNotFoundError:
            pass
    raise HTTPException(status_code=404, detail=f"任务不存在：{job_id}")


@app.get("/api/studio/catalog")
async def studio_catalog():
    """选本页目录：content/scenarios/ 下全部 gen_* 包（kanshan/template 不入册）。"""
    _require_studio()
    try:
        from studio.paths import SCENARIOS
    except Exception:
        SCENARIOS = None  # type: ignore[assignment]
    items: list[dict] = []
    if SCENARIOS is not None and SCENARIOS.is_dir():
        for d in sorted(SCENARIOS.glob("gen_*")):
            if not d.is_dir():
                continue
            sid = d.name
            title = sid
            try:
                title = (json.loads(
                    (d / "scenario.json").read_text(encoding="utf-8")
                ).get("title") or sid)
            except Exception:
                pass
            gate_ok, created_at = False, None
            try:
                job = load_job(sid)
                gate_ok = bool((job.get("gate") or {}).get("ok"))
                created_at = job.get("created_at")
            except Exception:
                pass
            items.append({"scenario_id": sid, "title": title,
                          "status": "ready" if gate_ok else "failed",
                          "created_at": created_at})
    return {"ok": True, "items": items}


@app.get("/api/studio")
async def studio_list():
    """已生成本列表 + 预置种子。"""
    _require_studio()
    return {"ok": True, "items": list_jobs(), "presets": list(PRESET_SEEDS)}


@app.get("/api/studio/zhihu/hot")
async def studio_zhihu_hot():
    """知乎热榜选题（创作素材）。素材桥未配置/失败 → 空列表优雅降级，不阻塞创作。

    注意：必须注册在 /api/studio/{scenario_id} 通配路由之前，否则被吞。"""
    _require_studio()
    items: list = []
    notice = ""
    try:
        from server.zhihu_bridge import fetch_hot_async
        data = await fetch_hot_async(limit=12)
        if isinstance(data, list):
            for x in data:
                if isinstance(x, dict) and str(x.get("title") or "").strip():
                    items.append({"title": str(x["title"]).strip()})
                elif isinstance(x, str) and x.strip():
                    items.append({"title": x.strip()})
    except Exception as e:  # noqa: BLE001
        notice = f"知乎热榜暂不可用（{type(e).__name__}），可手写钩子"
    if not items:
        notice = notice or "知乎热榜暂不可用（未配置 ZHIHU_ACCESS_SECRET 或接口异常），可手写钩子"
    return {"ok": True, "items": items, "notice": notice}


# ---------------- 分阶段制作流水线（行业流程：真相先行 → 角色 → 幕次 → 过闸） ----------------
# 注意：以下路由必须注册在 /api/studio/{scenario_id} 通配之前。

def _studio_llm(use_llm: bool):
    if not use_llm:
        return None
    try:
        from agents.llm_client import LLMClient
        return LLMClient()
    except Exception:
        return None


def _studio_draft_meta(draft: dict) -> dict:
    """返回工作台编排元数据；阶段正文仍由作者视图单独返回。"""
    return {
        "generation": draft.get("generation") or {},
        "agents": draft.get("agents") or {},
        "locks": draft.get("locks") or {},
        "provenance": draft.get("provenance") or {},
        "validation": draft.get("validation") or {},
    }


def _studio_stage_name(stage: str) -> str:
    stage = str(stage or "").strip().lower()
    if stage not in ("truth", "cast", "acts", "assemble"):
        raise ValueError(f"未知生产阶段：{stage}")
    return stage


@app.post("/api/studio/draft")
async def studio_draft_create(req: Request):
    """阶段 1 立项确认：创建制作草稿（行业铁律：真相未定不写角色）。"""
    _require_studio()
    body = await req.json()
    seed = str((body or {}).get("seed") or "").strip()
    from studio.staged import create_draft
    try:
        draft = create_draft(seed, (body or {}).get("brief"),
                             inner_boss=bool((body or {}).get("inner_boss")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "draft_id": draft["draft_id"], "brief": draft["brief"],
            **_studio_draft_meta(draft)}


@app.get("/api/studio/draft/{draft_id}")
async def studio_draft_get(draft_id: str):
    _require_studio()
    from studio.staged import load_draft
    try:
        draft = load_draft(draft_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=f"草稿不存在：{e}")
    return {"ok": True, "draft": draft, **_studio_draft_meta(draft)}


@app.post("/api/studio/draft/{draft_id}/stage/truth")
async def studio_stage_truth(draft_id: str, req: Request):
    """阶段 2 真相设计：AI 生成设计总纲草案，返回可编辑 world。"""
    _require_studio()
    body = await req.json()
    from studio.staged import load_draft, stage_truth
    try:
        draft = load_draft(draft_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        draft = stage_truth(draft, llm=_studio_llm(bool((body or {}).get("use_llm"))), use_zhihu=bool((body or {}).get("use_zhihu")),
                            inner_boss=bool((draft["brief"].get("modules") or {}).get("inner_boss")))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"真相生成失败：{type(e).__name__}: {e}")
    w = draft["world"]
    return {"ok": True, "provider": draft["providers"].get("truth"),
            "world": w,
            **_studio_draft_meta(draft),
            "truth_brief": {
                "title": w.get("title"), "logline": w.get("logline"),
                "surface_truth": w.get("surface_truth"), "inner_truth": w.get("inner_truth"),
                "truth_summary": w.get("truth_summary") or w.get("inner_truth"),
                "culprit": w.get("culprit"),
                "truth_nodes": (w.get("truth_nodes") or [])[:8],
                "locations": w.get("locations"),
            }}


@app.post("/api/studio/draft/{draft_id}/stage/cast")
async def studio_stage_cast(draft_id: str, req: Request):
    """阶段 3 角色设定：基于（用户编辑后的）真相生成 4 嫌疑人草案。"""
    _require_studio()
    body = await req.json()
    from studio.staged import load_draft, stage_cast
    try:
        draft = load_draft(draft_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        draft = stage_cast(draft, world=(body or {}).get("world"),
                           llm=_studio_llm(bool((body or {}).get("use_llm"))), use_zhihu=bool((body or {}).get("use_zhihu")))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"角色生成失败：{type(e).__name__}: {e}")
    chars = [{
        "id": c.get("id"), "name": c.get("name"), "archetype": c.get("archetype"),
        "comedy_hook": c.get("comedy_hook"), "public_bio": c.get("public_bio"),
        "faction": c.get("faction"),
    } for c in (draft["detail"].get("characters") or [])]
    return {"ok": True, "provider": draft["providers"].get("cast"),
            "detail": draft["detail"], "characters": chars,
            **_studio_draft_meta(draft)}


@app.post("/api/studio/draft/{draft_id}/stage/acts")
async def studio_stage_acts(draft_id: str, req: Request):
    """阶段 4 线索与幕次：基于真相+角色生成三幕与线索分配草案。"""
    _require_studio()
    body = await req.json()
    from studio.staged import load_draft, stage_acts
    try:
        draft = load_draft(draft_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        draft = stage_acts(draft, world=(body or {}).get("world"),
                           detail=(body or {}).get("detail"),
                           llm=_studio_llm(bool((body or {}).get("use_llm"))), use_zhihu=bool((body or {}).get("use_zhihu")))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"幕次生成失败：{type(e).__name__}: {e}")
    acts_out = [{"id": a.get("id"), "name": a.get("name"), "stage": a.get("stage"),
                 "brief": a.get("brief"), "actions_allocated": a.get("actions_allocated")}
                for a in (draft["acts"].get("acts") or [])]
    return {"ok": True, "provider": draft["providers"].get("acts"),
            "acts": draft["acts"], "acts_brief": acts_out,
            "clues": (draft["acts"].get("clues") or [])[:12],
            **_studio_draft_meta(draft)}


@app.post("/api/studio/draft/{draft_id}/stage/{stage}/lock")
async def studio_stage_lock(draft_id: str, stage: str, req: Request):
    """作者人工锁定阶段输出；锁定由服务端持久化并记录 hash。"""
    _require_studio()
    body = await req.json()
    try:
        stage = _studio_stage_name(stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if stage == "assemble":
        raise HTTPException(status_code=400, detail="assemble 由编译闸门锁定")
    from studio.staged import load_draft, lock_draft_stage
    try:
        draft = load_draft(draft_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="草稿不存在")
    output = body.get("output") if isinstance(body, dict) else None
    try:
        draft = lock_draft_stage(draft, stage, output=output)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "draft": draft, **_studio_draft_meta(draft)}


@app.post("/api/studio/draft/{draft_id}/stage/{stage}/unlock")
async def studio_stage_unlock(draft_id: str, stage: str):
    """作者解锁阶段以修改；所有下游产物标记失效。"""
    _require_studio()
    try:
        stage = _studio_stage_name(stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if stage == "assemble":
        raise HTTPException(status_code=400, detail="assemble 无独立草稿锁")
    from studio.staged import load_draft, unlock_draft_stage
    try:
        draft = load_draft(draft_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        draft = unlock_draft_stage(draft, stage)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "draft": draft, **_studio_draft_meta(draft)}


@app.post("/api/studio/draft/{draft_id}/assemble")
async def studio_draft_assemble(draft_id: str, req: Request):
    """阶段 6 编译过闸：三段终稿 → apply_brief → compile → 双册 → 结构+叙事闸门。"""
    _require_studio()
    body = await req.json()
    from studio.staged import assemble, load_draft
    try:
        draft = load_draft(draft_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        job = assemble(draft, (body or {}).get("world"), (body or {}).get("detail"),
                       (body or {}).get("acts"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # 前置阶段未锁定、编排状态不可开始属于客户端流程错误。
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"编译失败：{type(e).__name__}: {e}")
    return {"ok": True, "scenario_id": job["id"], "status": job["status"],
            "gate": job["gate"], "provider": job["provider"], "job": job,
            **_studio_draft_meta(draft)}


@app.get("/api/studio/{scenario_id}")
async def studio_get(scenario_id: str):
    """圣经 + 闸门（作者视图）。"""
    _require_studio()
    try:
        job = load_job(scenario_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"剧本不存在：{scenario_id}")
    return {"ok": True, "job": job}


@app.get("/api/studio/{scenario_id}/public")
async def studio_public(scenario_id: str):
    """试玩水合包（阵营/里层/guilt 零透出）。"""
    _require_studio()
    try:
        pack = public_snapshot(scenario_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"剧本不存在：{scenario_id}")
    return {"ok": True, "pack": pack}


@app.get("/api/studio/{scenario_id}/books")
async def studio_books(scenario_id: str):
    """故事本封面列表（旧 gen_* 无 scripts/ 时 items=[]）。"""
    _require_studio()
    try:
        load_job(scenario_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"剧本不存在：{scenario_id}")
    items = list_book_covers(scenario_id) if list_book_covers else []
    return {"ok": True, "items": items}


@app.get("/api/studio/{scenario_id}/book/{char_id}")
async def studio_book(scenario_id: str, char_id: str):
    """单人故事本全本（player_view）；本不存在或角色无本 → 404。"""
    _require_studio()
    try:
        load_job(scenario_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"剧本不存在：{scenario_id}")
    try:
        book = load_player_book(scenario_id, char_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"故事本不存在：{char_id}")
    return {"ok": True, "book": book}


# P2-1（2026-09-14 压测取证）：player_id 无长度上限，10 万字符可进存档
# （内存放大 + 存档污染）。统一入口校验。
_PLAYER_ID_MAX = 64


def _norm_player_id(raw, default: str = "player:1") -> str:
    """规范化并校验 player_id（≤64 字符）；超长抛 400。"""
    pid = str(raw if raw is not None else default).strip() or default
    if not pid.startswith("player:"):
        pid = f"player:{pid}"
    if len(pid) > _PLAYER_ID_MAX:
        raise HTTPException(status_code=400,
                            detail=f"player_id 过长（≤{_PLAYER_ID_MAX} 字符）")
    return pid


@app.post("/api/session")
async def create_session(req: Request):
    """创建对局（mode=main|daily|quick）。"""
    store = _require("store")
    try:
        body = await req.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    mode = body.get("mode", "main")
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=(
            f"mode 必须为 {'/'.join(VALID_MODES)}，收到：{mode!r}"))
    try:
        scenario_id, scenario_path = validate_scenario_for_session(
            body.get("scenario_id"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    host = _norm_player_id(body.get("player_id"))
    want_char = str(body.get("char_id") or body.get("role") or "").strip()
    # 前端设置面板透传的 API 配置（会话级，内存态不落盘——凭证纪律）
    api_cfg = ingest_api_headers(req)
    mode_now = engine_mode()
    if mode_now == "mock":
        # 建局也放线程，避免重载生成包时阻塞 HTTP/WS 心跳。
        def _build_mock_session():
            mock_eng = game_server.get_mock_engine({"scenario_id": scenario_id})
            return mock_eng, mock_eng.create_session(mode, host)
        _, session = await asyncio.to_thread(_build_mock_session)
    else:
        if EngineDriver is None or not getattr(app.state, "engine_available", False):
            raise HTTPException(status_code=503, detail=(
                "真实引擎当前不可装载（多为其他窗口对 engine/ 的并发编辑中间态）——"
                "可临时设 ZHIHU_GAME_USE_MOCK_ENGINE=1 启用 mock 通道；原因："
                f"{getattr(app.state, 'engine_error', 'unknown')}"))
        # EngineDriver 会同步读取整套场景/角色/记忆/知识卡文件；必须在线程池
        # 中完成，避免 Windows 慢盘或大剧本初始化拖住整个事件循环。
        def _build_engine_session():
            eng = EngineDriver(scenario_path)
            return eng, eng.create_session(mode, host)
        eng, session = await asyncio.to_thread(_build_engine_session)
        game_server.engines[session["session_id"]] = eng
    session["scenario_id"] = scenario_id
    welcome = make_event("system", session["session_id"], 1, "kanshan", {
        "event": "session_created", "mode": mode, "engine": session["engine"],
        "stage": session["stage"], "stage_name": session["stage_name"],
        "notice": ("mock 状态机驱动（ZHIHU_GAME_USE_MOCK_ENGINE=1）"
                   if mode_now == "mock" else
                   "B 窗口引擎（engine/ 七模块）已接线，全部裁决为引擎确定性结算"),
        "mock": mode_now == "mock"})
    session["events"].append(welcome)
    if mode == "party":
        # MEGA_MODE §二 联机同场：房间码进房（2-5 真人，AI 补齐空位）
        # 房间码防碰撞：毫秒种子 + 线性探测，避免同一秒连点建出同码
        base = int(time.time() * 1000) % 1000000
        code = f"{base:06d}"
        _probe = 0
        while code in ROOM_CODE_INDEX and _probe < 1000:
            _probe += 1
            code = f"{(base + _probe) % 1000000:06d}"
        session["room_code"] = code
        ROOM_CODE_INDEX[code] = session["session_id"]  # 房间码 → session 映射
        session["max_players"] = max(2, min(5, int(body.get("max_players", 5))))
        session["spectators"] = []
        session["ai_takeover"] = {}  # player_id -> True（掉线 AI 接管标记）
        welcome["payload"]["room_code"] = session["room_code"]
        welcome["payload"]["max_players"] = session["max_players"]
        welcome["payload"]["notice"] += f"；房间码 {session['room_code']}（好友进房后 join）"
        if mode_now != "mock":
            # G13 修复：房主建房即自动入席（faction 引擎暗置，前端零透出）
            seat = eng.join_seat(host, want_char or None)
            session["party"] = eng.party_snapshot()
            session["seats_public"] = eng.seats_public()
            if seat.get("char_id"):
                session.setdefault("booklet_roles", {})[host] = seat["char_id"]
            welcome["payload"]["seat"] = {k: seat.get(k) for k in
                                          ("ok", "char_id", "ai_takeover", "rejoin") if k in seat}
    elif want_char:
        from .booklet_svc import claim_role
        try:
            claim_role(session, host, want_char)
        except Exception:
            pass
    if mode != "party" and mode_now != "mock":
        # AI 席与真人同权（终局多数决需要 AI 席数）：登记本局空席 AI 总数
        try:
            from .booklet_svc import vacant_ai_roles
            session["ai_seat_count"] = len(vacant_ai_roles(session))
        except Exception:
            pass
    if api_cfg:
        app.state.api_cfg = getattr(app.state, "api_cfg", {})
        app.state.api_cfg[session["session_id"]] = api_cfg  # 内存态；session 档只存掩码
        session["api_cfg_masked"] = {k: (v[:6] + "***" if "key" in k or "secret" in k else v)
                                     for k, v in api_cfg.items()}
    store.save_session(session["session_id"], session)
    await game_server.broadcast(session["session_id"], [welcome])
    result = {"ok": True, "session": public_session_view(session),
              "events": [welcome]}
    book = _http_player_book(session.get("scenario_id"),
                             _seat_char_id(session, host, welcome))
    if book is not None:
        result["player_book"] = book
    return result


# ------------------------------------------------------ v2.1 增量路由（party/OAuth）
def _resolve_room_code(code: str) -> str | None:
    """6 位房间码 → session_id。内存索引优先；未命中则扫 SessionStore 兜底重建
    （服务重启后仍能凭码进房）。返回 None 表示无此房间。"""
    code = str(code).strip()
    sid = ROOM_CODE_INDEX.get(code)
    if sid:
        return sid
    store = getattr(app.state, "store", None)
    if store is None:
        return None
    try:
        for name in store.list_sessions():
            s = store.load_session(name)
            if s and s.get("mode") == "party" and s.get("room_code") == code:
                ROOM_CODE_INDEX[code] = s["session_id"]
                return s["session_id"]
    except Exception:
        pass
    return None


def _recover_claimed_char(session: dict, player_id: str) -> str:
    """重连时找回此人已认领的角色，避免无 char_id 的二次 join 被当成新人占座。"""
    pid = str(player_id or "")
    roles = session.get("booklet_roles") or {}
    if roles.get(pid):
        return str(roles[pid])
    for s in list(session.get("seats_public") or []) + list(session.get("seats") or []):
        if isinstance(s, dict) and s.get("player_id") == pid and s.get("char_id"):
            return str(s["char_id"])
    party = session.get("party") or {}
    seat = (party.get("seats") or {}).get(pid) if isinstance(party, dict) else None
    if isinstance(seat, dict) and seat.get("char_id"):
        return str(seat["char_id"])
    for cid, owner in (party.get("char_owner") or {}).items():
        if owner == pid:
            return str(cid)
    return ""


def _usable_ipv4(ip: str) -> bool:
    """拒绝网段地址 / 广播 / 组播。172.19.0.0 这类探测结果不能拿去分享。"""
    parts = str(ip or "").split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    if nums[0] == 0 or nums[0] >= 224:
        return False
    if nums[3] in (0, 255):
        return False
    return True


def _host_ipv4(host_hdr: str) -> str | None:
    h = str(host_hdr or "").strip()
    if not h or h.startswith("["):
        return None
    if ":" in h:
        h = h.rsplit(":", 1)[0]
    if h in ("localhost", "127.0.0.1"):
        return None
    return h if _usable_ipv4(h) else None


def _lan_score(ip: str) -> int:
    """192.168 > 10. > 其它 172.16-31 > Docker/Hyper-V 常用段。"""
    if not _usable_ipv4(ip):
        return -1
    a, b = (int(p) for p in ip.split(".")[:2])
    if a == 192 and b == 168:
        return 100
    if a == 10:
        return 80
    if a == 172 and 16 <= b <= 31:
        return 15 if b in (17, 18, 19) else 40
    return 5


def _lan_candidates() -> list[str]:
    import socket
    found: list[str] = []

    def add(ip: str) -> None:
        if _usable_ipv4(ip) and ip not in found:
            found.append(ip)

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except Exception:
        pass
    for probe in ("8.8.8.8", "192.168.1.1", "10.0.0.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect((probe, 80))
            add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    found.sort(key=_lan_score, reverse=True)
    return found


def _pick_lan_ip(host_hdr: str) -> tuple[str | None, bool]:
    host_ip = _host_ipv4(host_hdr)
    if host_ip:
        return host_ip, True
    cands = _lan_candidates()
    if not cands:
        return None, False
    return cands[0], True


@app.get("/api/lan-info")
async def lan_info(request: Request):
    """返回本机局域网可访问地址，供房主界面显示"朋友该连哪个地址"。

    优先用请求 Host（若房主已用可用单播 IP 访问则原样回显）；
    否则在本机网卡里挑 192.168/10，丢掉 172.19.0.0 这类网段地址和 Docker 虚卡。
    """
    host_hdr = request.headers.get("host", "")
    port = None
    if ":" in host_hdr and not host_hdr.startswith("["):
        port = host_hdr.rsplit(":", 1)[-1]
    port = port or str(os.environ.get("PORT", 8899))
    lan_ip, lan_ok = _pick_lan_ip(host_hdr)
    if not lan_ip:
        lan_ip = "127.0.0.1"
    return {"ok": True, "lan_ip": lan_ip, "port": port, "lan_ok": lan_ok,
            "base_url": f"http://{lan_ip}:{port}",
            "host_header": host_hdr,
            "notice": ("同一局域网的好友用 base_url 打开即可；跨网段需内网穿透"
                       if lan_ok else
                       "未探测到可用内网 IP，请把本机地址发给好友，勿使用网段地址")}


@app.get("/api/room/{code}")
async def resolve_room(code: str, request: Request):
    """房间码反查：好友只拿到 6 位码时，前端凭此拿到真实 session_id 与 ws 地址。

    返回 ws_url 供前端直接连接，免去手动拼 /ws/{session_id}。
    """
    store = _require("store")
    sid = _resolve_room_code(code)
    if not sid:
        raise HTTPException(status_code=404, detail=f"房间不存在或已过期：{code}")
    session = store.load_session(sid)
    if session is None:
        raise HTTPException(status_code=404, detail=f"房间对局已失效：{code}")
    # 以请求 Host 推导 ws 地址：局域网下即房主机器的 IP:端口，好友原样可用
    host = request.headers.get("host", "")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/ws/{sid}" if host else None
    return {"ok": True, "room_code": str(code).strip(), "session_id": sid,
            "ws_url": ws_url, "mode": session.get("mode"),
            "status": session.get("status"),
            "players": [p["player_id"] for p in session.get("players", [])],
            "max_players": session.get("max_players", 5)}


@app.post("/api/session/{session_id}/join")
async def join_session(session_id: str, req: Request):
    """party 房间码进房（2-5 真人各认领一名角色，AI 补齐空位；观战不限人数）。"""
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    if session.get("mode") != "party":
        raise HTTPException(status_code=400, detail="该对局不是 party 模式")
    try:
        body = await req.json()
    except ValueError:
        body = {}
    room_code = str(body.get("room_code", "")).strip()
    player_id = str(body.get("player_id", "")).strip()
    role = str(body.get("role", "player")).strip()  # player | spectator
    if room_code != session.get("room_code"):
        raise HTTPException(status_code=403, detail="房间码错误")
    if not player_id.startswith(("player:", "spectator:")):
        player_id = f"player:{player_id}" if role == "player" else f"spectator:{player_id}"
    if len(player_id) > _PLAYER_ID_MAX:
        raise HTTPException(status_code=400,
                            detail=f"player_id 过长（≤{_PLAYER_ID_MAX} 字符）")
    if role == "spectator":
        if player_id not in session.get("spectators", []):
            session.setdefault("spectators", []).append(player_id)
    else:
        if session.get("status") != "playing":
            raise HTTPException(status_code=409, detail="对局已结束，无法加入")
        if len(session["players"]) >= session.get("max_players", 5) and \
                all(p["player_id"] != player_id for p in session["players"]):
            raise HTTPException(status_code=409, detail=(
                f"房间已满（{session.get('max_players', 5)} 人）——可切换观战 role=spectator"))
        if all(p["player_id"] != player_id for p in session["players"]):
            session["players"].append({"player_id": player_id, "faction": "truth",
                                       "joined_at": time.time()})
        session.get("ai_takeover", {}).pop(player_id, None)  # 重连取消 AI 接管
    # 引擎席位（PartyBoard）：真人认领角色 + 阵营暗置发牌（faction 零透出）
    seats = None
    seat_res = None
    claimed = str(body.get("char_id") or "").strip() or _recover_claimed_char(session, player_id)
    if role == "player" and session.get("engine") == "engine_v3" and EngineDriver is not None:
        try:
            eng = game_server.get_engine(session)
            seat_res = eng.join_seat(player_id, claimed or None)
            if not seat_res.get("ok"):
                raise HTTPException(status_code=409, detail=(
                    f"席位分配失败（{seat_res.get('reason')}）——"
                    f"该角色已被真人认领或房间无空位"))
            session["party"] = eng.party_snapshot()
            if seat_res.get("char_id"):
                session.setdefault("booklet_roles", {})[player_id] = seat_res["char_id"]
            seats = eng.seats_public()
            session["seats_public"] = seats
        except HTTPException:
            raise
        except Exception as e:  # 席位异常如实上报（不影响加入本身）
            seats = [{"error": f"{type(e).__name__}: {e}"}]
            seat_res = None
    evt = make_event("system", session_id, session.get("round", 1), "kanshan", {
        "event": "player_rejoined" if role == "player" else "spectator_joined",
        "player_id": player_id, "role": role,
        "seats": seats,
        "players": [p["player_id"] for p in session["players"]]})
    session["events"].append(evt)
    store.save_session(session_id, session)
    await game_server.broadcast(session_id, [evt])
    result = {"ok": True, "session_id": session_id, "player_id": player_id,
              "role": role, "room_code": session.get("room_code"),
              "seats": seats,
              "players": [p["player_id"] for p in session["players"]]}
    if claimed and seat_res and seat_res.get("ok"):
        book = _http_player_book(session.get("scenario_id"),
                                 seat_res.get("char_id") or claimed)
        if book is not None:
            result["player_book"] = book
    return result


@app.post("/api/session/{session_id}/login")
async def session_login(session_id: str, req: Request):
    """OAuth code 换 token（契约 v2.1）：token 仅存内存，profile 三件套入 session 缓存。"""
    game_server.oauth = _require("oauth")
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    try:
        body = await req.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    player_id = _norm_player_id(body.get("player_id"))
    code = str(body.get("code") or body.get("authorization_code") or "").strip()
    # 1) 交换 token
    tok = await game_server.oauth.exchange(code)
    if not tok.get("ok"):
        raise HTTPException(status_code=502, detail=tok["notice"])
    # 2) 拉取公开三件套（缓存进 session，避免重复调用户数据 API）
    prof = await game_server.oauth.fetch_profile(tok["data"]["access_token"])
    if not prof.get("ok"):
        raise HTTPException(status_code=502, detail=prof["notice"])
    # token 仅内存（MEGA 铁律：不落盘/不回传前端）
    game_server.oauth_tokens[(session_id, player_id)] = tok["data"]
    profile = prof["data"]
    session.setdefault("profiles", {})[player_id] = profile  # session 内缓存
    events = [
        make_event("login_success", session_id, session.get("round", 1),
                   player_id, {
                       "player_id": player_id,
                       "uid": profile["uid"], "fullname": profile["fullname"],
                       "notice": "知乎登录成功（仅取公开三件套，email/phone 字段已忽略）"}),
        make_event("dossier_ready", session_id, session.get("round", 1),
                   "kanshan", {
                       "player_id": player_id,
                       "dossier": ZhihuOAuth.dossier(profile),
                       "notice": "《求真档案局特聘侦探证》已签发（花名为确定性占位，"
                                 "C 组 AI 个性化生成接入后替换）"}),
    ]
    session["events"].extend(events)
    store.save_session(session_id, session)
    await game_server.broadcast(session_id, events)
    return {"ok": True, "player_id": player_id, "profile": profile,
            "dossier": ZhihuOAuth.dossier(profile), "events": events}


@app.get("/api/profile/me")
async def profile_me(request: Request):
    """授权用户资料（隐私三件套缓存优先；无缓存时用内存 token 现拉一次）。"""
    game_server.oauth = _require("oauth")
    session_id = request.query_params.get("session_id", "")
    player_id = request.query_params.get("player_id", "player:1")
    store = _require("store")
    session = store.load_session(session_id) if session_id else None
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    cached = session.get("profiles", {}).get(player_id)
    if cached:
        return {"ok": True, "source": "session_cache", "profile": cached,
                "dossier": ZhihuOAuth.dossier(cached),
                "notice": "隐私三件套（session 内缓存）——email/phone 字段从未落盘"}
    tok = game_server.oauth_tokens.get((session_id, player_id))
    if not tok:
        return {"ok": False, "source": "none",
                "notice": "该玩家尚未在本对局完成 OAuth 登录（POST /api/session/{id}/login）",
                "authorize_url": game_server.oauth.authorize_url() or None,
                "oauth_configured": game_server.oauth.configured()}
    prof = await game_server.oauth.fetch_profile(tok["access_token"])
    if not prof.get("ok"):
        raise HTTPException(status_code=502, detail=prof["notice"])
    session.setdefault("profiles", {})[player_id] = prof["data"]
    store.save_session(session_id, session)
    return {"ok": True, "source": "api", "profile": prof["data"],
            "dossier": ZhihuOAuth.dossier(prof["data"])}

@app.get("/api/zhihu/recommendations")
async def zhihu_recommendations(request: Request, query: str = "", count: int = 5):
    ingest_api_headers(request)
    gw = _require("gateway")
    if request.headers.get("X-ZHIHU-SECRET"):
        gw.access_secret = request.headers["X-ZHIHU-SECRET"]
    return await gw.question_recommend(query=query or None, count=count)

@app.get("/api/zhihu/hot-list")
async def zhihu_hot_list(request: Request, limit: int = 20):
    """官方热榜：仅返回网关过滤后的公开榜单。"""
    ingest_api_headers(request)
    gw = _require("gateway")
    if request.headers.get("X-ZHIHU-SECRET"):
        gw.access_secret = request.headers["X-ZHIHU-SECRET"]
    return await gw.hot_list(limit=max(1, min(limit, 50)))

@app.get("/api/zhihu/creator-stats")
async def zhihu_creator_stats(request: Request, content_url: str):
    ingest_api_headers(request)
    gw = _require("gateway")
    if request.headers.get("X-ZHIHU-SECRET"):
        gw.access_secret = request.headers["X-ZHIHU-SECRET"]
    return await gw.creator_stats("", content_url)


# ------------------------------------------------------ minis 只读路由（V31 §9.4）
# 数据源（C 组口径）：rt.memory_puzzle_pool(tier) 取题 + rt.heart_quiz_flow 判定结算。
# 免登录路径（tier=open）无需 session、零额度；tier=full 仅登录局内热身关可用。


def _minis_rt():
    rt = getattr(app.state, "minis_rt", None)
    if rt is None:
        raise HTTPException(status_code=503, detail=(
            "minis 数据源未就绪（AgentRuntime 装载失败，见服务日志）"))
    return rt


def _quiz_face(item: dict) -> dict:
    """题面白名单：npc/said/heart——answer（答案位）与 teaching（结算教学点）
    仅服务端持有，出题零透出。"""
    return {"npc": item.get("npc", ""), "said": item.get("said", ""),
            "heart": item.get("heart", "")}


@app.get("/api/minis/memory-puzzle")
async def minis_memory_puzzle(request: Request):
    """心声窥听器取题：rt.memory_puzzle_pool(tier) 洗牌池随机抽一题。

    - tier=open（默认）：免登录外链直达，无案情词题面，无需 session、零额度；
    - tier=full：仅登录局内热身关——要求 session_id + player_id 且已完成
      OAuth 登录（session profiles 缓存命中），否则 403 真实拒绝；
    - 题面白名单 {npc, said, heart}：answer/teaching 零透出，判定走服务端。
    """
    rt = _minis_rt()
    tier = request.query_params.get("tier", "open")
    if tier not in ("open", "full"):
        raise HTTPException(status_code=400, detail="tier 仅支持 open | full")
    if tier == "full":  # full 仅登录局内（C 组口径）
        session_id = request.query_params.get("session_id", "")
        player_id = request.query_params.get("player_id", "")
        store = _require("store")
        session = store.load_session(session_id) if session_id else None
        logged_in = bool(session and player_id and
                         session.get("profiles", {}).get(player_id))
        if not logged_in:
            raise HTTPException(status_code=403, detail=(
                "tier=full 仅登录局内热身关可用（请先 POST /api/session/{id}/login"
                " 完成 OAuth 登录）；免登录请用 tier=open"))
    pool = rt.memory_puzzle_pool(tier)
    if not pool:
        raise HTTPException(status_code=503, detail=f"tier={tier} 题池为空（题库未装载）")
    import random as _random
    item = _random.choice(pool)
    return JSONResponse(
        {"ok": True, "game": "memory-puzzle", "tier": tier,
         "item": _quiz_face(item), "pool_size": len(pool),
         "notice": ("免登录外链题面（open 无案情词）" if tier == "open" else
                    "登录局内热身关题面") +
                   "；answer/teaching 零透出，判定走 POST /api/minis/heart-quiz"},
        headers={"Cache-Control": "public, max-age=300"} if tier == "open"
        else {"Cache-Control": "no-store"})


@app.post("/api/minis/heart-quiz")
async def minis_heart_quiz(req: Request):
    """M2 单题判定与结算：rt.heart_quiz_flow(item, answer)——答案位确定性比对，
    D 组结算句演出（答完揭教学点）。full 题判定要求登录态。"""
    rt = _minis_rt()
    try:
        body = await req.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    item = body.get("item") or {}
    answer = str(body.get("answer", "")).strip()
    if not isinstance(item, dict) or not item.get("npc") or not item.get("said"):
        raise HTTPException(status_code=400, detail=(
            "item 必须为取题返回的题面（npc/said/heart）"))
    # 服务端按 (npc, said) 反查原题（含答案位），前端回传题面不含答案
    original = next((q for q in rt.memory_puzzle_pool(item.get("tier", "open"))
                     + rt.memory_puzzle_pool("open") + rt.memory_puzzle_pool("full")
                     if q.get("npc") == item.get("npc")
                     and q.get("said") == item.get("said")), None)
    if original is None:
        raise HTTPException(status_code=404, detail="题面无法匹配题库（伪造或已过期）")
    if original.get("tier") == "full":
        session_id = str(body.get("session_id", ""))
        player_id = str(body.get("player_id", ""))
        store = _require("store")
        session = store.load_session(session_id) if session_id else None
        if not (session and session.get("profiles", {}).get(player_id)):
            raise HTTPException(status_code=403, detail=(
                "full 题判定仅登录局内可用（请先完成 OAuth 登录）"))
    res = rt.heart_quiz_flow(original, answer)
    return JSONResponse({"ok": True, "correct": res.get("correct"),
                         "npc": res.get("npc"), "teaching": res.get("teaching"),
                         "show": res.get("show"),
                         "notice": "判定与结算完成（D 组结算句演出）"})


@app.get("/api/minis/hotfeed-pool")
async def minis_hotfeed_pool(request: Request):
    """谣言消消乐数据源：热搜帖池脱敏抽样（author_mask 已脱敏，is_fake/clue_ref 零透出）。

    免鉴权 / 零额度 / 可缓存；不透 is_fake（辨别是玩法本身）与 clue_ref（主案联动）。
    """
    rt = _minis_rt()
    n = max(1, min(20, int(request.query_params.get("n", 8))))
    posts = list(getattr(rt.opinion, "_posts", {}).values())
    if not posts:
        raise HTTPException(status_code=503, detail="热搜帖池为空（内容未装载）")
    import random as _random
    _random.shuffle(posts)
    sampled = [{k: p.get(k) for k in
                ("id", "round", "title", "body", "author_mask", "topic_tag",
                 "humor_tag")}
               for p in posts[:n]]
    return JSONResponse(
        {"ok": True, "game": "hotfeed-pool", "total_pool": len(posts),
         "count": len(sampled), "posts": sampled,
         "notice": "脱敏抽样（author_mask 已脱敏；is_fake/clue_ref 不对外）"},
        headers={"Cache-Control": "public, max-age=300"})


@app.post("/api/session/{session_id}/whisper")
async def session_whisper(session_id: str, req: Request):
    """真人私聊路由（MEGA_MODE §二）：定向投递 chat 事件给目标玩家的 WS 连接。"""
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    try:
        body = await req.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    sender = str(body.get("from", "player:1")).strip()
    to = str(body.get("to", "")).strip()
    text = str(body.get("text", ""))[:500]
    ok, reason = check_text(text)
    if not ok:
        raise HTTPException(status_code=422, detail=(
            f"内容安全过滤：检测到{reason}，私聊已拦截（未消耗任何额度）"))
    if not to.startswith("player:"):
        raise HTTPException(status_code=400, detail="私聊目标必须是 player:{id}（真人）")
    if to == sender:
        raise HTTPException(status_code=400, detail="不能私聊自己")
    known = {p["player_id"] for p in session["players"]}
    if to not in known:
        raise HTTPException(status_code=404, detail=f"私聊目标不在本房间：{to}")
    evt = make_event("chat", session_id, session.get("round", 1),
                     sender if sender.startswith("player:") else f"player:{sender}", {
                         "whisper": True, "to": to, "text": text,
                         "notice": "真人私聊（定向投递，仅双方可见）"})
    session.setdefault("events", []).append(evt)  # 留档于 session（复盘可审计）
    store.save_session(session_id, session)
    await game_server.broadcast_to(session_id, [sender, to], [evt])
    delivered = game_server.rooms.get(session_id, {}).get("players", {}).get(to) is not None
    return {"ok": True, "delivered": bool(delivered),
            "notice": (None if delivered else
                       "目标当前不在线（事件已入 session 流，重连后可由前端补拉）")}


@app.post("/api/session/{session_id}/npc-whisper")
async def session_npc_whisper(session_id: str, req: Request):
    return await _npc_social_route(session_id, req, private=True)


@app.post("/api/session/{session_id}/npc-wave")
async def session_npc_wave(session_id: str, req: Request):
    return await _npc_social_route(session_id, req)


async def _npc_social_route(session_id: str, req: Request, private=False):
    _require("store")
    try:
        body = await req.json()
    except ValueError:
        raise HTTPException(400, "请求体必须是 JSON")
    ingest_api_headers(req, session_id)
    from .npc_social import social_request
    return await social_request(game_server, session_id, body, private=private)


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """对局状态（脱敏视图：暗置阵营快照 party/ 与玩家 faction 字段零透出）。"""
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404,
                            detail=f"对局不存在：{session_id}")
    view = public_session_view(session)
    if view.get("mode") == "party":
        view.setdefault("seats", None)
        eng = game_server.engines.get(session_id)
        if eng is not None:
            view["seats"] = eng.seats_public()
    return {"ok": True, "session": view}


@app.get("/api/session/{session_id}/booklet")
async def get_session_booklet(session_id: str, req: Request):
    """本人闭卷（可含自己的 faction）。列表/广播请用 booklet_svc.public_booklet_view。"""
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    player_id = str(req.query_params.get("player_id") or "").strip()
    if not player_id:
        players = session.get("players") or []
        player_id = ((players[0] or {}).get("player_id") if players else "") or "player:1"
    from .booklet_svc import visible_booklet
    return {"ok": True, "booklet": visible_booklet(session, player_id)}


@app.get("/api/session/{session_id}/booklets")
async def list_session_booklets(session_id: str):
    """选角目录：封面级，无 faction / never_say。"""
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    from .booklet_svc import library_of
    return {"ok": True, "items": library_of(session).catalog()}


@app.post("/api/session/{session_id}/claim")
async def claim_session_role(session_id: str, req: Request):
    """领取角色闭卷。单人写入 booklet_roles；房间局同时换座。"""
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    try:
        body = await req.json()
    except ValueError:
        body = {}
    player_id = str(body.get("player_id") or "").strip() or "player:1"
    if not player_id.startswith(("player:", "spectator:")):
        player_id = f"player:{player_id}"
    char_id = str(body.get("char_id") or body.get("role") or "").strip()
    if not char_id:
        raise HTTPException(status_code=400, detail="请选择角色")
    seats = None
    if session.get("mode") == "party" and session.get("engine") == "engine_v3" \
            and EngineDriver is not None:
        try:
            eng = game_server.get_engine(session)
            seat_res = eng.join_seat(player_id, char_id)
            if not seat_res.get("ok"):
                raise HTTPException(status_code=409, detail=(
                    f"席位分配失败（{seat_res.get('reason')}）——"
                    f"该角色已被真人认领或房间无空位"))
            session["party"] = eng.party_snapshot()
            char_id = str(seat_res.get("char_id") or char_id)
            session.setdefault("booklet_roles", {})[player_id] = char_id
            seats = eng.seats_public()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=409, detail=f"入席失败：{type(e).__name__}") from e
    from .booklet_svc import claim_role, visible_booklet
    rid = claim_role(session, player_id, char_id)
    store.save_session(session_id, session)
    result = {"ok": True, "char_id": rid, "player_id": player_id,
              "booklet": visible_booklet(session, player_id)}
    if seats is not None:
        result["seats"] = seats
    return result


@app.get("/api/session/{session_id}/voice/ice-servers")
async def voice_ice_servers(session_id: str):
    """Party 对讲 ICE：公共 STUN + 可选 TURN（TURN_* 仅环境变量）。

    mesh 客户端进房后拉此接口，勿把 TURN 口令写进前端源码。
    """
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404,
                            detail=f"对局不存在：{session_id}")
    if session.get("mode") != "party":
        raise HTTPException(status_code=400, detail="语音对讲仅 party 房间可用")
    return {"ok": True, "session_id": session_id, **ice_servers_from_env()}


@app.post("/api/session/{session_id}/action")
async def session_action(session_id: str, req: Request):
    """统一动作（search/chat/skill/counsel/vote/advance）。"""
    try:
        body = await req.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    action_type = str(body.get("type", ""))
    actor = str(body.get("actor", "player:1"))
    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload 必须是对象")
    _require("store")
    ingest_api_headers(req, session_id)
    events, error = await game_server.run_action(session_id, action_type,
                                                 actor, payload)
    if error is not None:
        raise HTTPException(status_code=error["status"], detail=error["notice"])
    session = app.state.store.load_session(session_id)
    return {"ok": True, "events": events, "session": public_session_view(session)}


@app.post("/api/session/{session_id}/ai_wave")
async def session_ai_wave(session_id: str, req: Request):
    """开打踢波：最多 3 个空席按本各走一步（有 key 调 API，否则启发式/skill）。"""
    store = _require("store")
    session = store.load_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"对局不存在：{session_id}")
    if session.get("status") != "playing":
        raise HTTPException(status_code=409, detail="对局已结束")
    ingest_api_headers(req, session_id)
    events = await game_server.run_ai_wave(session_id)
    acted = sorted({
        str((e.get("payload") or {}).get("booklet_role") or "")
        for e in events
        if (e.get("payload") or {}).get("booklet_act")
    } - {""})
    return {"ok": True, "events": events, "acted": acted}


@app.post("/api/session/{session_id}/ai_act")
async def session_ai_act(session_id: str, req: Request):
    """空席/指定角色按本行动。有 LLM header 走模型，否则启发式。"""
    try:
        body = await req.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    char_id = str(body.get("char_id") or body.get("role") or "").strip()
    if not char_id:
        raise HTTPException(status_code=400, detail="需要 char_id 或 role")
    dry_run = bool(body.get("dry_run", False))
    ingest_api_headers(req, session_id)
    result, error = await game_server.run_ai_act(
        session_id, char_id, dry_run=dry_run)
    if error is not None:
        raise HTTPException(status_code=error["status"], detail=error["notice"])
    return result


@app.get("/api/daily-topic")
async def daily_topic():
    """每日挑战词条：热榜白名单抽样；失败则诚实降级，不伪造热榜。"""
    topic = "#档案局夜班纪律#"
    body = "今日加练：把一条热搜词改写成档案局里的衍生谣言，再用知识卡拆穿它。"
    source = "fallback"
    notice = "热榜未接通，使用预置词条（不伪造实时热榜）"
    gw = getattr(game_server, "gateway", None) or getattr(app.state, "gateway", None)
    try:
        hot_fn = getattr(gw, "hot", None) or getattr(gw, "hot_list", None)
        if callable(hot_fn):
            raw = hot_fn()
            if hasattr(raw, "__await__"):
                raw = await raw
            items = []
            def _as_list(x):
                return x if isinstance(x, list) else []
            if isinstance(raw, dict):
                items = _as_list(raw.get("data")) or _as_list(raw.get("items")) or _as_list(raw.get("list"))
                if raw.get("ok") is False:
                    items = []
                    notice = str(raw.get("notice") or notice)
            elif isinstance(raw, list):
                items = raw
            titles = []
            for it in items:
                if isinstance(it, dict):
                    t = it.get("title") or it.get("query") or it.get("name")
                    if t and str(t).strip().lower() not in ("items", "data", "list", "ok", "notice"):
                        titles.append(str(t).strip())
                elif isinstance(it, str) and it.strip() and it.strip().lower() not in ("items", "data", "list", "ok", "notice"):
                    titles.append(it.strip())
            if titles:
                topic = titles[0] if titles[0].startswith("#") else f"#{titles[0].rstrip('#')}#"
                body = f"今日热榜挂钩：围绕「{titles[0]}」生成一则档案局衍生谣言，辟谣后可收工。"
                source = "hot_list"
                notice = "热榜词条已缓存（全服当日一份）"
    except Exception as e:
        notice = f"热榜读取失败，已降级预置词条（{type(e).__name__}）"
    return {"ok": True, "topic": topic, "body": body, "source": source, "notice": notice}


@app.get("/api/health")
async def health(request: Request, session_id: str | None = None):
    """健康检查（含 API 降级状态）。"""
    store = getattr(app.state, "store", None)
    gateway = getattr(app.state, "gateway", None)
    oauth = getattr(app.state, "oauth", None)
    sessions = store.list_sessions() if store else []
    mode = engine_mode()
    engine_info = {
        "mode": mode,
        "mock_enabled": mock_enabled(),
        "available": bool(getattr(app.state, "engine_available", True)),
        "notice": ("B 窗口引擎已接线（engine/ 七模块，确定性裁决）"
                   if mode == "engine" else
                   "mock 状态机驱动（ZHIHU_GAME_USE_MOCK_ENGINE=1）"),
    }
    if mode == "engine" and not engine_info["available"]:
        engine_info["error"] = getattr(app.state, "engine_error", "unknown")
    gw = gateway.health() if gateway else {"degraded": ["gateway-not-ready"]}
    from .ai_status import describe_ai
    # 健康探针也接收设置面板的本机配置；只在内存中用于诊断，不回显密钥。
    probe_cfg = ingest_api_headers(request)
    ai_cfg = dict((getattr(app.state, 'api_cfg', {}) or {}).get(session_id) or {})
    ai_cfg.update(probe_cfg)
    ai_info = describe_ai(os.environ,
        ai_cfg,
        store.load_session(session_id) if store and session_id else None)
    return {
        "status": "ok",
        "service": "zhihu-game-server",
        "engine": engine_info,
        "oauth": {
            "configured": oauth.configured() if oauth else False,
            "app_id": bool(oauth.app_id) if oauth else False,
            "redirect_uri": bool(oauth.redirect_uri) if oauth else False,
            "access_secret": bool(oauth.access_secret) if oauth else False,
            "notice": ("OAuth 登录可用（App Key 仅后端，不进前端/日志）"
                       if oauth and oauth.configured() and oauth.access_secret
                       else "OAuth 凭证未配置齐（ZHIHU_OAUTH_APP_ID/"
                            "ZHIHU_OAUTH_APP_KEY/ZHIHU_OAUTH_REDIRECT_URI"
                            "/ZHIHU_ACCESS_SECRET）——login 路由将返回真实降级"),
        },
        # 信息面收敛（P2）：ids 只保留最近 5 个，防全量 session id 泄露
        "sessions": {"active": len(sessions), "ids": sessions[-5:]},
        "voice_peers": (getattr(app.state, "voice_hub", None) or voice_hub).peer_count(),
        "gateway": gw,
        "ai": ai_info,
        "dotenv": {"available": bool(_DOTENV_STATUS["available"]),
                    "loaded": bool(_DOTENV_STATUS["loaded"]),
                    "error": _DOTENV_STATUS["error"] or None},
        "degraded": bool(gw.get("degraded")) or not gw.get(
            "credentials_configured", False),
        "uptime_s": round(time.time() - getattr(app.state, "started_at",
                                                time.time()), 1),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

@app.get("/api/zhihu/quota")
async def zhihu_quota():
    """查询知乎官方实时额度（不消耗业务额度）。"""
    gw = getattr(app.state, "gateway", None)
    if gw is None:
        raise HTTPException(503, "知乎网关未就绪")
    return await gw.live_quota()


@app.post("/api/ai/test")
async def ai_test(request: Request):
    """设置页真实 Agent 探针：发送最小请求，不写入对局事件。"""
    cfg = ingest_api_headers(request)
    probe = None
    # 面板三件套齐全 = 用户显式指定自建端点（如 DeepSeek）→ 探针/对局都
    # 优先走 main，不被残留的知乎 Secret 抢占（否则测的/用的都不是用户填的）。
    has_panel_main = bool(cfg.get("llm_key") and cfg.get("llm_base")
                          and cfg.get("llm_model"))
    if cfg.get("zhihu_secret") and not has_panel_main:
        key = cfg.get("llm_key") or cfg.get("zhihu_secret") or os.environ.get("LLM_API_KEY", "")
        base = cfg.get("llm_base") or os.environ.get("LLM_BASE_URL", "")
        model = cfg.get("llm_model") or os.environ.get("LLM_MODEL", "")
        if not (cfg.get("llm_key") and cfg.get("llm_base") and cfg.get("llm_model")):
            base = "https://developer.zhihu.com/v1"
            model = cfg.get("llm_model") or os.environ.get("ZHIHU_LLM_MODEL", "zhida-agent")
            key = key or cfg["zhihu_secret"]
    else:
        if cfg.get("llm_key") and cfg.get("llm_base") and cfg.get("llm_model"):
            # 面板三件套（如 DeepSeek 等自建 OpenAI 兼容端点）：用面板凭证
            # 构造临时实例探针，不写进程 env（避免污染其他对局的回落通道）。
            # use_credentials 锁定实例凭证——chat 内部 _sync_env 不得用进程
            # env 静默顶替（否则探针打的不是用户填的端点，结果失真）。
            from agents.llm_client import LLMClient as _LC, OpenAICompatProvider as _OP
            _p = _OP()
            _p.use_credentials(cfg["llm_key"], cfg["llm_base"], cfg["llm_model"])
            probe = _LC(providers={"main": _p, "mock": _LC().providers["mock"]})
            model = cfg["llm_model"]
        else:
            # 页面加载即探测（早于任何对局动作，进程 env 可能尚未初始化）：
            # 与对局内 AI 同源——走 _llm_for_session 的赛事默认通道（.env 凭证回落），
            # 避免探针在 env 未初始化时用 mock 兜底误报"AI 调用失败"。
            probe = game_server._llm_for_session("__ai_test__")
            if probe is None:
                raise HTTPException(400, "未配置完整的知乎 Agent 凭证")
            model = os.environ.get("LLM_MODEL", "zhida-agent")
    if cfg.get("zhihu_secret"):
        os.environ.update(LLM_API_KEY=key, LLM_BASE_URL=base.rstrip("/"), LLM_MODEL=model)
    try:
        from agents.llm_client import call_gateway
        started = time.monotonic()
        panel_used = bool(cfg.get("zhihu_secret") or cfg.get("llm_key"))
        panel_err = ""
        # 官方知乎 Agent 走网关 direct_answer，统一认证、额度和错误信封。
        gw = getattr(app.state, "gateway", None)
        try:
            if gw is not None and cfg.get("zhihu_secret"):
                gw.access_secret = cfg["zhihu_secret"]
                # 加随机 nonce 并跳过缓存，确保这是一次真实官方网络请求。
                nonce = uuid.uuid4().hex[:10]
                result = await gw.direct_answer(f"请只回复：知乎 Agent 已连接。测试编号 {nonce}", "你是知乎 Agent 连通性测试。", bypass_cache=True)
                if not result.get("ok"):
                    raise RuntimeError(result.get("notice") or "官方 Agent 返回失败")
                reply = (result.get("data") or {}).get("content", "")
                provider = "zhida"
            else:
                reply = call_gateway(probe, "你是知乎 Agent 连通性测试。", "请只回复：知乎 Agent 已连接。", provider="main", temperature=0)
                provider = getattr(probe, "last_provider", "main")
        except HTTPException:
            raise
        except Exception as panel_exc:
            if not panel_used:
                raise
            # 面板/设置里保存的凭证失效（过期 key / 误填）→ 自动回落赛事
            # 默认通道（.env 凭证，与对局内 AI 同源），探针不再因旧凭证 502。
            panel_err = f"{type(panel_exc).__name__}: {panel_exc}"
            # 面板探针可能已把失效凭证写进进程 env——先清掉并从 .env 恢复
            # 真实凭证，再回落赛事默认通道，否则回落也会拿脏 env 再次失败。
            for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "ZHIHU_APP_KEY"):
                os.environ.pop(k, None)
            try:
                from dotenv import load_dotenv
                load_dotenv(_ENV_FILE, override=True)
            except Exception:
                pass
            probe = game_server._llm_for_session("__ai_test__")
            if probe is None:
                raise HTTPException(502, f"面板凭证无效（{panel_err}），且后端未配置默认通道")
            reply = call_gateway(probe, "你是知乎 Agent 连通性测试。", "请只回复：知乎 Agent 已连接。", provider="main", temperature=0)
            provider = getattr(probe, "last_provider", "main")
        elapsed_ms = round((time.monotonic() - started) * 1000)
        if not reply or provider in ("mock", "fallback"):
            raise RuntimeError(
                "接口返回了兜底内容"
                + (f"（{getattr(probe, 'last_error', '')}）"
                   if getattr(probe, "last_error", "") else ""))
        # identity_leak：探针命中的话说明该通道此刻会把产品身份说出口——
        # 对局内已有 reply_guard 兜底，此处只如实上报诊断，不改变探针语义。
        return {"ok": True, "provider": provider, "source": "api", "network_request": True,
                "model": model, "elapsed_ms": max(1, elapsed_ms),
                "identity_leak": has_product_identity(reply),
                "panel_fallback": bool(panel_err), "panel_error": panel_err,
                "reply": str(reply)[:120]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"知乎 Agent 请求失败：{type(exc).__name__}: {exc}")


@app.websocket("/ws/{session_id}")
async def ws_endpoint(ws: WebSocket, session_id: str):
    """事件流（契约 §3.7）。

    query 参数：player_id=player:X（玩家身份，掉线接管广播用）；spectator=1（观战只读，
    MEGA_MODE §二：旁听视角，不产生动作）。首条推送快照 system 事件；之后按 §3.6 双向。
    """
    await ws.accept()
    store = getattr(app.state, "store", None)
    if store is None:
        await ws.close(code=1013)
        return
    session = store.load_session(session_id)
    if session is None:
        not_found = make_event("system", session_id, 0, "kanshan",
                               {"event": "session_not_found",
                                "notice": f"对局不存在：{session_id}"})
        await ws.send_text(json.dumps(not_found, ensure_ascii=False))
        await ws.close(code=4404)
        return
    ws.state.player_id = ws.query_params.get("player_id") or None
    ws.state.spectator = ws.query_params.get("spectator") in ("1", "true")
    await game_server.on_connect(ws, session_id)
    try:
        snapshot = make_event("system", session_id, session.get("round", 1),
                              "kanshan", {
            "event": "snapshot",
            "stage": session.get("stage"),
            "stage_name": session.get("stage_name"),
            "round": session.get("round"),
            "actions_left": session.get("actions_left"),
            "heat": session.get("heat"),
            "players": [p["player_id"] for p in session.get("players", [])],
            "spectators": session.get("spectators", []),
            "seats": session.get("seats_public") or session.get("seats") or [],
            "clues_gained": session.get("clues_gained", []),
            "status": session.get("status"),
            "engine": session.get("engine", "mock"),
            "spectator": ws.state.spectator,
            "room_code": session.get("room_code"),
        })
        await ws.send_text(json.dumps(snapshot, ensure_ascii=False))
        joined = make_event("system", session_id, session.get("round", 1),
                            "kanshan", {
            "event": "spectator_joined" if ws.state.spectator else "peer_joined",
            "player_id": ws.state.player_id,
            "mock": mock_enabled()})
        await game_server.broadcast(session_id, [joined])
        while True:
            raw = await ws.receive_text()
            if ws.state.spectator and raw.strip() != "ping":
                await game_server._send_error(ws, session_id,
                                              "观战视角为只读（不产生动作）")
                continue
            await game_server.handle(ws, raw)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass  # 非文本帧等异常帧：诚实断开，不让房间残留死连接
    finally:
        game_server.on_disconnect(ws, session_id)
        # 掉线 AI 接管广播（MEGA_MODE §二）：真人离场 → 该角色由 AI 无缝接管
        player_id = getattr(ws.state, "player_id", None)
        if player_id and not getattr(ws.state, "spectator", False):
            fresh = store.load_session(session_id)
            if fresh and fresh.get("status") == "playing" and any(
                    p["player_id"] == player_id for p in fresh.get("players", [])):
                remaining = game_server.rooms.get(session_id, {}).get(
                    "players", {}).get(player_id)
                if remaining is None:  # 该玩家已无其他在线连接
                    fresh.setdefault("ai_takeover", {})[player_id] = True
                    takeover_seat = None
                    if fresh.get("engine") == "engine_v3" and EngineDriver is not None:
                        try:  # PartyBoard 席位标记（faction 结果引擎内部留存，零透出）
                            eng = game_server.get_engine(fresh)
                            res = eng.leave_seat(player_id)
                            takeover_seat = res.get("char_id")
                            fresh["party"] = eng.party_snapshot()
                        except Exception:
                            pass
                    evt = make_event("system", session_id,
                                     fresh.get("round", 1), "kanshan", {
                        "event": "ai_takeover", "player_id": player_id,
                        "char_id": takeover_seat,
                        "notice": "该角色已由 AI 接管",
                        "source": fresh.get("engine", "mock")})
                    fresh["events"].append(evt)
                    store.save_session(session_id, fresh)
                    await game_server.broadcast(session_id, [evt])


@app.websocket("/ws/{session_id}/voice")
async def voice_ws_endpoint(ws: WebSocket, session_id: str):
    """Party 对讲信令（独立通道，不进 §3.6 / 引擎 / SessionStore / 回声链）。

    query：player_id=（须已入座；已登记观战可连，只听不说）。
    只转发 join / leave / offer / answer / ice / mute。
    """
    store = getattr(app.state, "store", None)
    session = store.load_session(session_id) if store is not None else None
    if store is None:
        await ws.accept()
        await ws.close(code=1013)
        return
    await voice_hub.handle_connect(ws, session_id, session)


if __name__ == "__main__":
    import uvicorn
    import os as _os
    uvicorn.run(app, host="0.0.0.0", port=int(_os.environ.get("PORT", 8899)))
