#!/usr/bin/env python3
"""宣传片录制用的本机服务启动器（仅 127.0.0.1:8899）。

存在的理由：直接用 `python -m uvicorn` 时 traceback 会丢进沙箱日志黑洞，
这里强制把 uvicorn 日志写到 game/data/_promo_server.log，方便定位 500。
不是游戏的一部分，删掉不影响游戏。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GAME))

log_path = GAME / "data" / "_promo_server.log"
logging.basicConfig(
    filename=str(log_path), filemode="w", level=logging.DEBUG, force=True,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "server.main:app", host="127.0.0.1", port=8899,
        log_level="info", access_log=True, log_config=None,
    )
