"""回归守护：run_ai_act 的 PlayerAgent.decide 必须走线程池（不阻塞事件循环）。

背景（2026-09-14 P1 实跑取证）：decide 内部为同步 LLM 调用，最坏
LLM_TIMEOUT=30s + 429 退避 ~24s；修复前直接在事件循环线程执行会冻结
全部房间的 WS 心跳与请求（审计脚本 tools/audit_decide_blocking.py 的
mutation Run B 实测：3s 慢网关期间心跳 tick=0）。修复后 to_thread 心跳
tick=49。本守护防止未来改回同步调用。

运行时级取证见 tools/audit_decide_blocking.py（python tools/audit_decide_blocking.py）。
"""
from __future__ import annotations

import ast
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parents[1]
MAIN = GAME_ROOT / "server" / "main.py"


def _is_to_thread_call(node: ast.Await) -> bool:
    call = node.value
    if not (isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "to_thread"):
        return False
    mod = call.func.value
    return (isinstance(mod, ast.Name) and mod.id == "asyncio") or \
           (isinstance(mod, ast.Attribute) and mod.attr == "asyncio")


def test_decide_wrapped_in_to_thread():
    """agent.decide(...) 必须形如 `await asyncio.to_thread(agent.decide, ...)`。"""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    decides: list[ast.Assign] = []

    class _V(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            src = ast.unparse(node)
            if "agent.decide" in src:
                decides.append(node)
            self.generic_visit(node)

    _V().visit(tree)
    assert len(decides) == 1, f"期望恰好 1 处 agent.decide 赋值，实得 {len(decides)}"
    assert isinstance(decides[0].value, ast.Await), \
        "agent.decide 必须被 await（异步执行）"
    assert _is_to_thread_call(decides[0].value), \
        "agent.decide 必须包在 asyncio.to_thread(...) 内，"
    "否则同步 LLM 调用会阻塞事件循环（复现 tools/audit_decide_blocking.py Run B）"
