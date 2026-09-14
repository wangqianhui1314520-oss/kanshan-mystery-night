"""Party 房间语音信令 Hub。

独立通道：只转发 join / leave / offer / answer / ice / mute，
不写 SessionStore、不碰 PartyBoard、不进回声链、不进游戏引擎。

前端连接：
  WS  /ws/{session_id}/voice?player_id=player:1
  GET /api/session/{session_id}/voice/ice-servers   （party-only；STUN + 可选 TURN）

TURN 仅读环境变量 TURN_URL / TURN_USER / TURN_PASS，未配则只回公共 STUN。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

SIGNAL_TYPES = frozenset({"join", "leave", "offer", "answer", "ice", "mute"})
# 观战只听不说：不可发起通话 / 上报麦状态（answer+ice 仍允许，以便收下联音频）
LISTEN_ONLY_FORBIDDEN = frozenset({"offer", "mute"})
NEED_TARGET = frozenset({"offer", "answer", "ice"})

DEFAULT_STUN_URLS = (
    "stun:stun.l.google.com:19302",
    "stun:stun.cloudflare.com:3478",
)

_CLOSE_NOT_FOUND = 4404
_CLOSE_BAD_REQUEST = 4400
_CLOSE_FORBIDDEN = 4403


def ice_servers_from_env() -> dict[str, Any]:
    """公共 STUN + 可选 TURN（凭证只从环境变量读，不写进前端源码）。"""
    servers: list[dict[str, Any]] = [{"urls": list(DEFAULT_STUN_URLS)}]
    turn_url = str(os.environ.get("TURN_URL") or "").strip()
    turn_user = str(os.environ.get("TURN_USER") or "").strip()
    turn_pass = str(os.environ.get("TURN_PASS") or "").strip()
    turn_configured = bool(turn_url)
    if turn_url:
        entry: dict[str, Any] = {"urls": [turn_url]}
        if turn_user:
            entry["username"] = turn_user
        if turn_pass:
            entry["credential"] = turn_pass
        servers.append(entry)
    return {
        "ice_servers": servers,
        "turn_configured": turn_configured,
        "notice": (
            "已含 TURN，mesh 客户端可直接用 ice_servers"
            if turn_configured else
            "仅公共 STUN；跨网失败时请同网或配置 TURN_URL/TURN_USER/TURN_PASS"
        ),
    }


def seated_player_ids(session: dict) -> set[str]:
    """入座真人 id（只读 session['players']，不查 PartyBoard）。"""
    ids: set[str] = set()
    for p in session.get("players") or []:
        if isinstance(p, dict) and p.get("player_id"):
            ids.add(str(p["player_id"]))
    return ids


def spectator_ids(session: dict) -> set[str]:
    ids: set[str] = set()
    for x in session.get("spectators") or []:
        if isinstance(x, str) and x.strip():
            ids.add(x.strip())
        elif isinstance(x, dict) and x.get("player_id"):
            ids.add(str(x["player_id"]))
    return ids


def _candidates(raw: str) -> list[str]:
    pid = str(raw or "").strip()
    if not pid:
        return []
    if pid.startswith(("player:", "spectator:")):
        return [pid]
    return [f"player:{pid}", f"spectator:{pid}", pid]


def resolve_voice_identity(session: dict, raw_player_id: str) -> dict[str, Any] | None:
    """校验 player_id：已入座可说；已登记观战只听。未入席返回 None。"""
    seated = seated_player_ids(session)
    specs = spectator_ids(session)
    cands = _candidates(raw_player_id)
    for cid in cands:
        if cid in seated:
            return {"player_id": cid, "listen_only": False, "role": "player"}
    for cid in cands:
        if cid in specs:
            return {"player_id": cid, "listen_only": True, "role": "spectator"}
    return None


class VoiceHub:
    """按 session_id 记语音连接，广播/定向转发信令。"""

    def __init__(self) -> None:
        # session_id -> player_id -> {ws, listen_only}
        self.rooms: dict[str, dict[str, dict[str, Any]]] = {}

    def reset(self) -> None:
        self.rooms.clear()

    def peer_count(self) -> int:
        return sum(len(room) for room in self.rooms.values())

    def peer_list(self, session_id: str, except_id: str | None = None) -> list[dict[str, Any]]:
        room = self.rooms.get(session_id) or {}
        out: list[dict[str, Any]] = []
        for pid, meta in room.items():
            if except_id and pid == except_id:
                continue
            out.append({
                "player_id": pid,
                "listen_only": bool(meta.get("listen_only")),
            })
        return out

    def register(self, session_id: str, player_id: str, ws: WebSocket,
                 listen_only: bool) -> dict[str, Any] | None:
        room = self.rooms.setdefault(session_id, {})
        old = room.get(player_id)
        room[player_id] = {"ws": ws, "listen_only": listen_only}
        return old if old and old.get("ws") is not ws else None

    def unregister(self, session_id: str, player_id: str, ws: WebSocket) -> bool:
        room = self.rooms.get(session_id)
        if not room:
            return False
        cur = room.get(player_id)
        if cur is None or cur.get("ws") is not ws:
            return False
        room.pop(player_id, None)
        if not room:
            self.rooms.pop(session_id, None)
        return True

    async def handle_connect(self, ws: WebSocket, session_id: str,
                             session: dict | None) -> None:
        """accept → 校验 → peers 快照 + join 广播 → 转发循环。"""
        await ws.accept()
        if session is None:
            await self._reject(ws, _CLOSE_NOT_FOUND, f"对局不存在：{session_id}")
            return
        if session.get("mode") != "party":
            await self._reject(ws, _CLOSE_FORBIDDEN, "语音对讲仅 party 房间可用")
            return
        raw_pid = ws.query_params.get("player_id") or ""
        ident = resolve_voice_identity(session, raw_pid)
        if ident is None:
            if not str(raw_pid).strip():
                await self._reject(ws, _CLOSE_BAD_REQUEST, "缺少 player_id")
            else:
                await self._reject(
                    ws, _CLOSE_FORBIDDEN,
                    "仅已入座玩家可对讲；观战须为已登记 spectator（只听不说）")
            return
        if ws.query_params.get("listen_only") in ("1", "true"):
            ident["listen_only"] = True
        player_id = ident["player_id"]
        listen_only = bool(ident["listen_only"])

        old = self.register(session_id, player_id, ws, listen_only)
        if old is not None:
            try:
                await old["ws"].close(code=1000)
            except Exception:
                pass
        try:
            await self._send(ws, {
                "type": "peers",
                "session_id": session_id,
                "from": "server",
                "payload": {
                    "you": player_id,
                    "listen_only": listen_only,
                    "role": ident["role"],
                    "peers": self.peer_list(session_id, except_id=player_id),
                },
            })
            await self.broadcast(session_id, {
                "type": "join",
                "session_id": session_id,
                "from": player_id,
                "payload": {"listen_only": listen_only},
            }, exclude=player_id)
            while True:
                raw = await ws.receive_text()
                await self._handle_message(
                    ws, session_id, player_id, listen_only, raw)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            if self.unregister(session_id, player_id, ws):
                await self.broadcast(session_id, {
                    "type": "leave",
                    "session_id": session_id,
                    "from": player_id,
                    "payload": {},
                }, exclude=player_id)

    async def _handle_message(self, ws: WebSocket, session_id: str,
                              player_id: str, listen_only: bool, raw: str) -> None:
        if raw.strip() == "ping":
            await self._send(ws, {
                "type": "pong",
                "session_id": session_id,
                "from": "server",
                "payload": {"server_time": time.time()},
            })
            return
        try:
            msg = json.loads(raw)
        except ValueError:
            await self._error(ws, session_id, "消息不是合法 JSON")
            return
        if not isinstance(msg, dict):
            await self._error(ws, session_id, "消息必须是 JSON 对象")
            return
        typ = str(msg.get("type") or "")
        if typ not in SIGNAL_TYPES:
            await self._error(
                ws, session_id,
                f"未支持的信令类型：{typ or '(空)'}（仅 join/leave/offer/answer/ice/mute）")
            return
        if listen_only and typ in LISTEN_ONLY_FORBIDDEN:
            await self._error(ws, session_id, "观战只听不说（不可发起 offer / mute）")
            return

        to = msg.get("to")
        if to is not None:
            to = str(to).strip() or None
        payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}

        if typ == "leave":
            try:
                await ws.close(code=1000)
            except Exception:
                pass
            return

        if typ == "join":
            await self.broadcast(session_id, {
                "type": "join",
                "session_id": session_id,
                "from": player_id,
                "payload": {"listen_only": listen_only},
            }, exclude=player_id)
            return

        if typ in NEED_TARGET:
            if not to:
                await self._error(ws, session_id, f"{typ} 必须指定 to（对端 player_id）")
                return
            if to == player_id:
                await self._error(ws, session_id, "不能发给自己")
                return
            ok = await self.send_to(session_id, to, {
                "type": typ,
                "session_id": session_id,
                "from": player_id,
                "to": to,
                "payload": payload,
            })
            if not ok:
                await self._error(ws, session_id, f"对端不在对讲房间：{to}")
            return

        # mute：广播麦状态（from 以入房身份为准，不信任客户端）
        muted = payload.get("muted")
        if not isinstance(muted, bool):
            muted = bool(payload.get("muted", True))
        await self.broadcast(session_id, {
            "type": "mute",
            "session_id": session_id,
            "from": player_id,
            "payload": {"muted": muted},
        }, exclude=player_id)

    async def send_to(self, session_id: str, player_id: str, msg: dict) -> bool:
        room = self.rooms.get(session_id) or {}
        meta = room.get(player_id)
        if meta is None:
            return False
        return await self._send(meta["ws"], msg)

    async def broadcast(self, session_id: str, msg: dict,
                        exclude: str | None = None) -> None:
        room = self.rooms.get(session_id) or {}
        dead: list[str] = []
        for pid, meta in list(room.items()):
            if exclude and pid == exclude:
                continue
            if not await self._send(meta["ws"], msg):
                dead.append(pid)
        for pid in dead:
            room.pop(pid, None)
        if session_id in self.rooms and not self.rooms[session_id]:
            self.rooms.pop(session_id, None)

    async def _reject(self, ws: WebSocket, code: int, notice: str) -> None:
        await self._send(ws, {
            "type": "error",
            "session_id": "",
            "from": "server",
            "payload": {"notice": notice, "code": code},
        })
        try:
            await ws.close(code=code)
        except Exception:
            pass

    async def _error(self, ws: WebSocket, session_id: str, notice: str) -> None:
        await self._send(ws, {
            "type": "error",
            "session_id": session_id,
            "from": "server",
            "payload": {"event": "error", "notice": notice},
        })

    @staticmethod
    async def _send(ws: WebSocket, obj: dict) -> bool:
        try:
            await ws.send_text(json.dumps(obj, ensure_ascii=False))
            return True
        except Exception:
            return False
