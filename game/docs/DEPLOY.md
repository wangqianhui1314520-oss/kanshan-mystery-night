# 上线部署指南（看山失踪夜 · 阿里云 ECS）

> 部署路线：**GitHub（私有仓库）→ 阿里云 ECS 拉起**。
> 本文所有结论来自本机实跑取证（2026-09-14，江苏电信网络环境）。

## 一、先明确架构事实

- **所有外部 API 调用（知乎开放平台 / 直答 LLM）都在服务端**，前端零出站：
  浏览器只连同源 `POST /api/session` + `WebSocket /ws/{session_id}`（`frontend/js/net.js`）。
- **前端由同一个 FastAPI 进程托管**（`/assets` `/js` `/css` `/minis` + 根路径 index.html），
  不需要单独部署前端，**单域名 + 单容器**即可。
- 前端在 https 页面下自动用 `wss://` 同源（`net.js` / `store.js:partyWsUrl`），
  **只要域名有 TLS，WebSocket 不用任何额外配置**。

## 二、凭证红线（先读这段）

| 内容 | 在哪 | 能否进仓库/服务器 |
|---|---|---|
| `game/.env`（真实 Access Secret） | 仅本机 | ❌ 已被 gitignore 挡住，**绝不 push**；上服务器用 scp 直传或手动填 |
| `game/.env.example` | 仓库内 | ✅ 模板，可参照填写 |
| `data/sessions`、`data/memory` | 仅本地运行时 | ❌ 运行产物，服务器上自动生成 |
| `agents/cache` | 仅本地运行时 | ❌ 运行产物 |

全仓 1090 个文本文件扫描过凭证模式，**唯一命中就是 `game/.env`**，其余零硬编码密钥。

## 三、阿里云 ECS 部署步骤

### 0. 服务器要求
- 2C2G 起（引擎是纯 Python，内存占用小）；系统任意（示例用 Ubuntu/Debian）。
- 安全组放行：`80`、`443`（对外）；`22`（运维）。**8899 不要对外开放**，走 Nginx 反代。

### 1. 装 Docker（服务器上）
```bash
curl -fsSL https://get.docker.com | bash
systemctl enable --now docker
```

### 2. 拉代码
```bash
git clone https://github.com/wangqianhui1314520-oss/kanshan-mystery-night.git
cd kanshan-mystery-night
```
国内 ECS 拉 GitHub 慢/失败时，二选一：
```bash
# a) ghproxy 镜像（域名可能变化，失效就换）
git clone https://gh-proxy.com/https://github.com/wangqianhui1314520-oss/kanshan-mystery-night.git
# b) 本地打包直传（最稳）
# 本机：git archive --format=tar.gz -o kanshan.tar.gz master
#      scp kanshan.tar.gz root@<服务器IP>:/opt/ && 服务器上 tar xzf
```

### 3. 配置凭证（仓库里没有 .env，这一步必须手动）
```bash
cp game/.env.example game/.env
vi game/.env        # 填 ZHIHU_ACCESS_SECRET / ZHIHU_LLM_MODEL / ZHIHU_GAME_MODEL 等
chmod 600 game/.env
```
或从本机直传（更快，且和本地调试值完全一致）：
```bash
# 本机执行
scp game/.env root@<服务器IP>:/opt/kanshan-mystery-night/game/.env
```

### 4. 起容器（docker compose 一键部署，推荐）
```bash
cd game
docker compose up -d --build
# 验证
docker compose ps                        # STATUS 应为 Up (healthy)，约 15s 后健康检查转绿
curl http://127.0.0.1:8899/api/health    # 期望 {"status":"ok",...,"engine":{"available":true}}
docker compose logs -f kanshan           # 实时日志排查
```
挂载说明（见 `game/docker-compose.yml`）：`./volumes/data → /app/data` 存对局存档（`data/sessions`、`data/memory`），
`./volumes/cache → /app/agents/cache` 存 LLM 缓存与额度统计 —— 都挂出来，容器重建不丢。

⚠️ 硬约束：rooms + EngineDriver 全在进程内存 → **单实例运行，严禁 `--scale` / 多副本**。
⚠️ 端口只绑 `127.0.0.1`，对外统一走 Nginx 反代（安全组不要开 8899）。

备选（不装 compose 插件时，用裸 docker run）：
```bash
docker build -t kanshan ./game
docker run -d --name kanshan --restart always -p 127.0.0.1:8899:8899 \
  -v /data/kanshan:/app/data -v /data/kanshan-cache:/app/agents/cache kanshan
```

### 5. Nginx 反代（**WS 升级头是必须的，漏了直接 400**）
```nginx
server {
    listen 80;
    server_name <你的域名或IP>;
    location / {
        proxy_pass http://127.0.0.1:8899;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300s;      # 必须 > LLM_TIMEOUT(30s)，否则长对话被判超时
        proxy_send_timeout 300s;
    }
}
```

### 6. HTTPS（正式对外必须）
`net.js` 在 https 页面下自动升 `wss://`；http 页面无法建 wss，会被浏览器拦。
```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d <你的域名>        # 免费证书，自动改写 Nginx
```
注意：国内域名需已完成 ICP 备案才能 80/443 对外提供 web 服务。

### 7. 更新流程
```bash
cd game && git pull && docker compose up -d --build
```

## 四、必须配置的环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `ZHIHU_ACCESS_SECRET` | ✅ | 内容接口 + 直答鉴权（本地 `game/.env` 已有，scp 即可） |
| `ZHIHU_LLM_MODEL` / `ZHIHU_GAME_MODEL` | ✅ | 直答模型名（`zhida-*`） |
| `ZHIHU_GAME_QUOTA_ZHIDA` | 建议 `400` | NPC 高频对话限额 |
| `PORT` | 容器内默认 8899 | `run.py` 读取 |
| `TURN_URL` / `TURN_USER` / `TURN_PASS` | 可选 | 不配则语音只给公共 STUN，跨网可能连不上 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 可选 | 自建 OpenAI 兼容通道 |
| `ZHIHU_OAUTH_*` | 可选 | 启用 OAuth 才需要；`REDIRECT_URI` 必须与控制台逐字符一致 |

## 五、已知坑（实跑踩出来的）

1. **`render.yaml` 的 `dockerfilePath` 相对【仓库根】而非 `dockerContext`** ——
   Dockerfile 在 `game/` 下，写 `./Dockerfile` 必然构建失败（已修为 `./game/Dockerfile`）。
2. **`msiexec` 在中文路径下报 `rc 1639`** —— Windows 上解包/安装 MSI 别放中文目录。
3. **大文件下载会静默截断** —— 残留的半截可执行文件报 `Exec format error`，
   极易误判成"环境不让执行"；先核对文件大小。
4. **`agents/cache` 记得挂卷** —— 否则容器重建丢 LLM 缓存与额度统计（有 OSError 兜底，不致命）。
5. **实例数必须 = 1** —— `server/main.py` 的 `self.rooms` 是进程内存 + `EngineDriver` 每局一套实例，
   水平扩容会导致对局状态分裂。将来要扩容必须先上 Redis pub/sub。

## 六、上线前检查清单

- [ ] `git status` 看不到 `.env`（本地）；服务器上 `game/.env` 存在且 `chmod 600`
- [ ] `curl http://127.0.0.1:8899/api/health` 返回 200 且 `engine.available = true`
- [ ] `curl https://<域名>/api/health` 通（TLS 生效）
- [ ] 浏览器打开后 F12 → Network → WS 那一行状态是 **101**（不是 400/404）
- [ ] 对局中 NPC 说话正常（直答额度在消耗）
- [ ] `/data/kanshan` 里出现 `sessions/*.json`（持久卷生效）
- [ ] 实例数 = 1
