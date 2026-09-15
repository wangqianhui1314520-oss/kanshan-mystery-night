"""session 建局回归守护：同步引擎装载必须移出 asyncio 事件循环。"""
from __future__ import annotations

import ast
from pathlib import Path


MAIN = Path(__file__).resolve().parents[1] / "server" / "main.py"


def _to_thread_awaits(tree: ast.AST) -> list[ast.Await]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "to_thread"):
            continue
        found.append(node)
    return found


def test_session_builders_are_called_via_to_thread():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    src = MAIN.read_text(encoding="utf-8")
    awaits = _to_thread_awaits(tree)
    assert any("_build_mock_session" in ast.unparse(node) for node in awaits)
    assert any("_build_engine_session" in ast.unparse(node) for node in awaits)
    assert "eng = EngineDriver(scenario_path)" in src
    assert "eng.create_session(mode, host)" in src
