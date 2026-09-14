"""部署入口（发布为应用）：读取沙箱注入的 PORT 环境变量启动 FastAPI。"""
import os

# 出网强制直连（2026-09-14 压测取证）：本机系统代理（Windows 注册表
# ProxyEnable=1 → 127.0.0.1:<port>）会被 urllib/httpx 默认自动继承，
# 导致知乎直答上游 401/405/异常秒回交替。游戏服务器对知乎开放平台的
# 出网必须直连，不受宿主代理配置影响。
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import uvicorn

from server.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8899)))
