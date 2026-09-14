"""pytest 桥接 — 把 engine/_smoke_test.py 的 176+ 断言暴露给 pytest 收集（G 组复用）。

用法（G 组 tests/ 或任意位置）：
    pytest game/engine/test_engine_suite.py -v
    pytest game/            # 全仓收集时本文件同样生效

设计：不搬运断言——直接 import _smoke_test 复用其 fixture 构造与 test_* 驱动函数，
每个驱动函数包装为一个 pytest test；check() 失败累积在 suite.FAILED，
包装器在函数运行后统一断言（失败详情随消息输出）。直跑模式
（python engine/_smoke_test.py）不受影响。
"""
from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import _smoke_test as suite  # noqa: E402


@pytest.fixture(scope="module")
def suite_tmp():
    """模块级临时 fixture（等价于直跑模式 main() 的 TemporaryDirectory）。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        suite.build_fixture(tmp)
        yield tmp


def _driver_names() -> list[str]:
    return sorted(n for n, f in vars(suite).items()
                  if n.startswith("test_") and inspect.isfunction(f))


def _run_driver(name: str, tmp: Path | None) -> tuple[int, int]:
    """运行一个驱动函数并返回 (passed, failed)；check() 失败累积进 suite.FAILED。"""
    suite.PASSED.clear()
    suite.FAILED.clear()
    fn = getattr(suite, name)
    kwargs = {}
    if "tmp" in inspect.signature(fn).parameters:
        kwargs["tmp"] = tmp
    fn(**kwargs)
    return len(suite.PASSED), len(suite.FAILED)


def _make_test(name: str):
    def _case(suite_tmp):  # 参数名与 fixture 同名 → pytest 自动注入
        passed, failed = _run_driver(name, suite_tmp)
        detail = "; ".join(suite.FAILED)
        assert not failed, f"{name}: {failed} 个断言失败（通过 {passed}）→ {detail}"
        assert passed > 0, f"{name}: 未产生任何断言（驱动函数异常？）"

    _case.__name__ = name
    _case.__doc__ = (suite.__dict__[name].__doc__ or "").strip() or f"冒烟驱动 {name}"
    return _case


for _name in _driver_names():
    globals()[_name] = _make_test(_name)


def test_smoke_suite_inventory():
    """桥接自检：确认 _smoke_test 的驱动函数全部被收集。"""
    names = _driver_names()
    assert len(names) >= 9, f"桥接驱动不足：{names}"
    assert "test_stage_machine" in names and "test_resolver" in names
