"""部署入口（发布为应用）：读取沙箱注入的 PORT 环境变量启动 FastAPI。"""
import os

import uvicorn

from server.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8899)))
