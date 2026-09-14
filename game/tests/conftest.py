"""G 测试组共享夹具：路径引导 + 真实 kanshan 内容装配。

运行（约定于 game/ 目录）：
    pytest tests/ -v
零 AI、零网络：全部裁决走引擎确定性路径；降级演练仅做传输层故障注入。

测试环境默认恢复 LLM 磁盘缓存回放（确定性基线依赖 agents/cache/llm_cache.json
的历史录制）。线上运行时不受影响：LLMClient 默认关闭缓存、直连 API，需显式
LLM_CACHE=1 才启用缓存。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# 必须在任何 LLMClient 实例化之前生效（conftest 先于测试模块导入）。
os.environ.setdefault("LLM_CACHE", "1")

GAME_ROOT = Path(__file__).resolve().parents[1]
if str(GAME_ROOT) not in sys.path:
    sys.path.insert(0, str(GAME_ROOT))

SCENARIO_DIR = GAME_ROOT / "content" / "scenarios" / "kanshan"

# 固定种子：抽卡/阵营发牌/模拟全部可复现（mutation test 基线）
SEED = 20260912


@pytest.fixture(scope="session")
def game_root() -> Path:
    return GAME_ROOT


@pytest.fixture(scope="session")
def scenario_dir() -> Path:
    return SCENARIO_DIR


@pytest.fixture(scope="session")
def scenario() -> dict:
    return json.loads((SCENARIO_DIR / "scenario.json").read_text(encoding="utf-8"))


@pytest.fixture()
def fresh_driver():
    """真实内容 EngineDriver（每测试独立实例，互不污染）。"""
    from server.engine_driver import EngineDriver

    def _make(session_id: str = "s_gtest"):
        return EngineDriver(SCENARIO_DIR), session_id

    return _make


@pytest.fixture(scope="session")
def char_factions() -> dict:
    """8 角色卡预设阵营（PartyBoard 被裹挟者优先级输入）。"""
    out = {}
    for f in sorted((SCENARIO_DIR / "characters").glob("char_*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        out[c["id"]] = c.get("faction", "swayable")
    return out


@pytest.fixture(scope="session")
def achievements_data() -> dict:
    """D 组 achievements.md JSON 契约解析（唯一数据源；围栏用正则提取，
    避开正文中对 ```json 字样的引用）。"""
    import re

    text = (SCENARIO_DIR / "scripts" / "achievements.md").read_text(encoding="utf-8")
    items = None
    for block in re.findall(r"```json\n(.*?)\n```", text, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and data and all(isinstance(x, dict) and x.get("id")
                                                   for x in data):
            items = data
            break
    assert items, "achievements.md 未找到可解析的成就 JSON 围栏块"
    return {"items": items, "raw": text}
