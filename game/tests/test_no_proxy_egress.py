"""守护测试：LLM/OAuth/网关出网必须直连，不得继承系统代理。

背景（2026-09-14 压测取证）：Windows 注册表系统代理（ProxyEnable=1 →
127.0.0.1:<port>）被 urllib/httpx 默认继承，本机代理对 developer.zhihu.com
的 POST 返回 401/405/异常秒回，直接导致 NPC 聊天全军覆没。
mutation 对照：回退 llm_client.py 50 行到裸 urlopen 时，本机代理开启
环境下请求被代理接管（405/502），本测试失败——证明守护有效。
"""
import urllib.request

import httpx


def test_straight_opener_ignores_system_proxy():
    """_STRAIGHT_OPENER 不得携带任何代理 handler。"""
    from agents.llm_client import _STRAIGHT_OPENER
    for h in _STRAIGHT_OPENER.handlers:
        if isinstance(h, urllib.request.ProxyHandler):
            assert h.proxies in ({}, None), \
                f"直连 opener 携带了代理配置：{h.proxies}"


def test_straight_opener_differs_from_default_when_proxy_present():
    """若系统存在代理配置，默认 urlopen 的 effective proxies 与直连 opener 不同。"""
    from agents.llm_client import _STRAIGHT_OPENER
    sys_proxies = urllib.request.getproxies()
    opener_proxies = {}
    for h in _STRAIGHT_OPENER.handlers:
        if isinstance(h, urllib.request.ProxyHandler) and h.proxies:
            opener_proxies = h.proxies
    # 直连 opener 永远无代理；系统有代理时二者必须不同（守护的意义所在）
    assert opener_proxies == {}
    if sys_proxies:
        assert set(sys_proxies) != set(opener_proxies) or sys_proxies == {}


def test_gateway_httpx_clients_disable_trust_env():
    """zhihu_gateway 的 AsyncClient/Client 必须显式 trust_env=False。"""
    import inspect
    from server.gateway import zhihu_gateway as zg
    src = inspect.getsource(zg)
    assert src.count("trust_env=False") >= 3, \
        "zhihu_gateway 存在未禁用 trust_env 的 httpx 出网点"


def test_oauth_httpx_clients_disable_trust_env():
    """oauth 的 AsyncClient 必须显式 trust_env=False。"""
    import inspect
    from server import oauth
    src = inspect.getsource(oauth)
    assert src.count("trust_env=False") >= 2, \
        "oauth 存在未禁用 trust_env 的 httpx 出网点"


def test_runpy_sets_no_proxy_wildcard():
    """部署入口 run.py 必须设 NO_PROXY=*（环境层双保险）。"""
    from pathlib import Path
    run_py = Path(__file__).resolve().parents[1] / "run.py"
    src = run_py.read_text(encoding="utf-8")
    assert 'os.environ["NO_PROXY"] = "*"' in src
    assert 'os.environ["no_proxy"] = "*"' in src
