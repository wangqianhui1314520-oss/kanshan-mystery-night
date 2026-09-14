"""对局状态持久化：会话存档与长期记忆。

存档：data/sessions/{room_id}.json（JSON 序列化，原子写入：tmp + os.replace）
长期记忆：data/memory/{user_id}.json（跨局，玩家画像）

骨架签名保持不变（__init__ / save_session / load_session / save_memory / load_memory）；
新增能力为增量：list_sessions / delete_session / append_event / exists。
room_id / user_id 做白名单校验（防路径穿越）；损坏存档按不存在处理（返回 None），不抛散。
"""
import json
import os
import re
import time
from pathlib import Path

_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class SessionStore:
    def __init__(self, root: Path):
        self.sessions_dir = root / "sessions"
        self.memory_dir = root / "memory"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- 内部工具
    @staticmethod
    def _safe(name: str) -> str | None:
        name = str(name or "").strip()
        return name if _SAFE_ID.match(name) else None

    def _path(self, directory: Path, name: str) -> Path:
        return directory / f"{name}.json"

    def _atomic_write(self, path: Path, obj):
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, path)

    # ------------------------------------------------------------- 会话存档
    def save_session(self, room_id: str, state: dict):
        name = self._safe(room_id)
        if name is None:
            raise ValueError(f"非法 room_id：{room_id!r}")
        self._atomic_write(self._path(self.sessions_dir, name),
                           {**state, "updated_at": time.time()})

    def load_session(self, room_id: str) -> dict | None:
        name = self._safe(room_id)
        if name is None:
            return None
        f = self._path(self.sessions_dir, name)
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None  # 损坏存档按不存在处理，不让服务端崩

    def exists(self, room_id: str) -> bool:
        name = self._safe(room_id)
        return bool(name) and self._path(self.sessions_dir, name).exists()

    def list_sessions(self) -> list[str]:
        return sorted(p.stem for p in self.sessions_dir.glob("*.json")
                      if not p.name.endswith(".tmp"))

    def delete_session(self, room_id: str) -> bool:
        name = self._safe(room_id)
        if name is None:
            return False
        f = self._path(self.sessions_dir, name)
        if f.exists():
            f.unlink()
            return True
        return False

    def append_event(self, room_id: str, event: dict, cap: int = 200) -> bool:
        """向存档内 events 追加一条（超上限截断最旧），不存在返回 False。"""
        state = self.load_session(room_id)
        if state is None:
            return False
        events = state.setdefault("events", [])
        events.append(event)
        if len(events) > cap:
            del events[: len(events) - cap]
        self.save_session(room_id, state)
        return True

    # ------------------------------------------------------------- 长期记忆
    def save_memory(self, user_id: str, memory: dict):
        name = self._safe(user_id)
        if name is None:
            raise ValueError(f"非法 user_id：{user_id!r}")
        self._atomic_write(self._path(self.memory_dir, name), memory)

    def load_memory(self, user_id: str) -> dict:
        name = self._safe(user_id)
        if name is None:
            return {}
        f = self._path(self.memory_dir, name)
        if not f.exists():
            return {}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
