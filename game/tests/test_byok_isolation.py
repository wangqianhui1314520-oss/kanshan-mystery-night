"""回归守护：BYOK 跨会话隔离（2026-09-15 P1/P2 修复）。

背景（实跑取证 data/_byok_isolation_audit.py + 静态审计）：
  P1 旧版把会话级玩家 key 持久写进程 env（os.environ["LLM_API_KEY"] 等 7 处），
     _llm_for_session 的 env fallback 会让未设 key 的会话借到最后设 key 玩家的
     凭证（额度被烧），多会话并发时 Provider 快照互相覆盖。
  P2 sid 后缀 = 毫秒时间戳 mod 1e8（engine_driver.py），GET /api/session/{sid}
     无鉴权，按创建时间窗 ±5s ≈ 1e4 候选即可枚举他局内容。

修复语义：
  P1 凭证经 Provider.use_credentials 显式注入（逐字段等价旧版 env 快照结果），
     env 只承载服务器 .env 默认值；共享 gateway 不再被会话 secret 改写。
  P2 sid 后缀改 secrets.token_hex(4)（加密随机，8 hex ≈ 4.3e9 空间）。

本守护防止两条路径回退：
  - main.py 重新出现玩家凭证写进程 env
  - sid 生成退回可预测时间戳

mutation 验证记录：恢复 `os.environ["LLM_API_KEY"] = key` →
test_no_env_writes_for_player_credentials FAIL；sid 改回
`int(now*1000)%100000000` → test_sid_not_predictable FAIL。
"""
from __future__ import annotations

import ast
import secrets
import time
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parents[1]
MAIN = GAME_ROOT / "server" / "main.py"
DRIVER = GAME_ROOT / "server" / "engine_driver.py"

_FORBIDDEN_ENV_KEYS = {"LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "ZHIHU_APP_KEY"}


def _env_string_writes(path: Path) -> list[str]:
    """收集 `os.environ["KEY"] = ...` 形态的字符串下标赋值（ast 精确匹配）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []

    class _V(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for tgt in node.targets:
                if (isinstance(tgt, ast.Subscript)
                        and isinstance(tgt.value, ast.Attribute)
                        and tgt.value.attr == "environ"
                        and isinstance(tgt.value.value, ast.Name)
                        and tgt.value.value.id == "os"
                        and isinstance(tgt.slice, ast.Constant)
                        and isinstance(tgt.slice.value, str)
                        and tgt.slice.value in _FORBIDDEN_ENV_KEYS):
                    hits.append(tgt.slice.value)
            self.generic_visit(node)

    _V().visit(tree)
    return hits


def test_no_env_writes_for_player_credentials():
    """main.py 不得把玩家级 LLM/ZHIHU 凭证写进进程 env（BYOK 会话隔离）。"""
    hits = _env_string_writes(MAIN)
    assert not hits, (
        f"main.py 出现玩家凭证写进程 env: {hits} —— 会造成跨会话凭证借用"
        "（未设 key 的会话 fallback 到 os.environ 即借到最后设 key 玩家的凭证）。"
        "请改用 Provider.use_credentials(...) 显式注入。")


def test_llm_for_session_uses_explicit_credentials():
    """_llm_for_session 必须走 use_credentials 显式注入路径。"""
    src = MAIN.read_text(encoding="utf-8")
    assert "use_credentials" in src, \
        "_llm_for_session 应通过 use_credentials 注入会话凭证（不落 env）"
    # gateway 共享单例不得被会话 secret 改写（旧版 self.gateway.access_secret = ...）
    assert ".gateway.access_secret = " not in src, \
        "共享 gateway 的 access_secret 不得被会话级凭证改写（跨会话污染点）"


def test_sid_not_predictable():
    """engine_driver 默认 sid 后缀必须是 secrets.token_hex(4)，不得是时间戳取模。"""
    src = DRIVER.read_text(encoding="utf-8")
    assert "secrets.token_hex(4)" in src, \
        "sid 后缀必须用 secrets.token_hex(4)（加密随机），否则可按创建时间枚举会话"
    assert "% 100000000" not in src, \
        "sid 不得再用毫秒时间戳 mod 1e8（时间窗爆破 1e4 候选即可遍历当日会话）"
    assert "import secrets" in src


def test_token_hex_suffix_random_and_shaped():
    """token_hex(4) 语义 sanity：8 位小写 hex、连续生成不重复（不可由时间预测）。"""
    a = secrets.token_hex(4)
    b = secrets.token_hex(4)
    assert len(a) == 8 and all(c in "0123456789abcdef" for c in a)
    assert a != b, "token_hex 连续生成重复（熵异常）"
    # 前缀习惯保留：s_YYYYMMDD_<8hex>（日志/排查可读）
    sid = f"s_{time.strftime('%Y%m%d')}_{secrets.token_hex(4)}"
    assert sid.startswith("s_") and len(sid) == len("s_YYYYMMDD_") + 8
