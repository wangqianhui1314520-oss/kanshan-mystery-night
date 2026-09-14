# 上线部署指南（看山失踪夜）

> 本文所有结论都来自本机实跑取证，不是纸面推断。取证时间：2026-09-14，网络环境：江苏电信。
> 关键实测数据在文末「实测记录」，踩过的坑在「已知坑」。

## 一、先明确架构事实

- **所有外部 API 调用（知乎开放平台 / 直答 LLM）都在服务端**，前端零出站：
  浏览器只连同源 `POST /api/session` + `WebSocket /ws/{session_id}`（`frontend/js/net.js`）。
- **前端由同一个 FastAPI 进程托管**（`/assets` `/js` `/css` `/minis` + 根路径 index.html），
  所以不需要单独部署前端，**单域名 + 单容器**即可。
- 前端在 https 页面下自动用 `wss://` 同源（`net.js:155`，`store.js:partyWsUrl`），
  **只要域名有 TLS，WebSocket 不用任何额外配置**。

因此"部署后端"= 把这个 FastAPI 容器跑在某个能提供 **HTTPS + WebSocket 长连接 + 持久磁盘** 的地方。

## 二、方案选型（本机实测可达性）

| 方案 | 成本 | 无需账号 | 浏览器警告页 | 本机可达性实测 | 适合 |
|---|---|---|---|---|---|
| **A. cloudflared 隧道** | ¥0 | ✅ | **无** | 3/5 成功，TLS 0.6s，间歇重置 | 现场演示、随时给链接 |
| **A'. serveo SSH 隧道** | ¥0 | ✅ | ❌ **有警告页** | 域名可达稳定 | 备选（体验差） |
| **B. Render 免费层** | ¥0 | ❌ 需 GitHub+Render | 无 | `onrender.com` 301 可达 | 长期公开链接 |
| **C. 国内轻量服务器** | ~¥10/月 | ❌ | 无 | 最快 | **正式上线推荐** |

**为什么不推荐纯静态托管**：Vercel / Netlify / GitHub Pages 不支持 WebSocket 长连接，本游戏必挂。

## 三、方案 A：一键隧道（零成本，已验证）

```bash
cd game
python tools/serve_public.py                # 自动优先 cloudflared，缺失则回退 serveo
python tools/serve_public.py --tunnel serveo    # 强制 SSH 隧道
python tools/serve_public.py --no-tunnel        # 只起本地服务（内网/服务器用）
```

脚本会：起服务 → 探活 `/api/health` → 建隧道 → 打印公网 HTTPS 地址 → 自检 → Ctrl+C 回收。

**实跑输出示例**：
```
[1/3] 启动 FastAPI 服务 端口 8899 …
      服务就绪 ✅  http://127.0.0.1:8899/api/health
[2/3] 建立 cloudflared 隧道 …
[3/3] 公网自检 …
  公网地址：https://scores-powers-department-announcements.trycloudflare.com
```

**限制（必须知道）**：
- 域名**每次重启都变**（quick tunnel 不支持固定域名）；本机必须保持开机。
- 本机网络到 Cloudflare 边缘**间歇性被重置**（实测 3/5 成功）——浏览器刷新通常能进。
- serveo 备选**会插浏览器警告页**（`Serveo - Warning`，需点 "Continue to Site"），给评委不体面。

## 四、方案 B：Render 免费层（长期链接）

用仓库根的 `render.free.yaml`（免费层兼容版；根 `render.yaml` 是付费版，带持久磁盘）。

1. 把仓库推到 GitHub（**私有仓库即可**，推送前确认 `.gitignore` 已忽略 `.env` —— 本仓库根 `.gitignore` 已覆盖）
2. Render 控制台 → New → Blueprint → 选该仓库 → 应用 `render.free.yaml`
3. 在 Environment 面板填 `ZHIHU_ACCESS_SECRET` / `ZHIHU_LLM_MODEL` / `ZHIHU_GAME_MODEL`
4. 部署后访问 `https://<name>.onrender.com/api/health` 确认 engine 为 `engine`

**免费层三个硬限制**：
- **15 分钟无入站流量即休眠**（WS 消息也算流量，所以对局中不会休眠；闲置会休眠）。
  休眠后冷启动 ~1 分钟，**且本地文件系统被清空** → `data/sessions` 存档丢失（对局是实时内存态，单局内不受影响，跨局存档不可用）。
- 不能水平扩容 —— 恰好与「`rooms` 是进程内存」的约束一致，无冲突。
- **大量出站 API 调用可能触发暂停**（本游戏每个 NPC 对话都调知乎直答），被暂停需升级付费恢复。这是免费层最大的不确定性。

## 五、方案 C：国内服务器（正式上线推荐）

```bash
# 服务器上
git clone <repo> && cd <repo>/game
cp .env.example .env && vi .env          # 填 ZHIHU_ACCESS_SECRET 等
docker build -t kanshan . && docker run -d --name kanshan -p 8899:8899 \
  --env-file .env -v /data/kanshan:/app/data --restart always kanshan
```

Nginx 反代（**Upgrade 头必须配，漏了 WS 直接 400**）：

```nginx
location / {
  proxy_pass http://127.0.0.1:8899;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_set_header Host $host;
  proxy_read_timeout 300s;    # 必须 > LLM_TIMEOUT(30s)，否则长对话被判超时
}
```

必须 `numInstances=1` / 单副本：`server/main.py` 的 `self.rooms` 是进程内存。

## 六、必须注入的环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `ZHIHU_ACCESS_SECRET` | ✅ | 内容接口 + 直答鉴权 |
| `ZHIHU_LLM_MODEL` / `ZHIHU_GAME_MODEL` | ✅ | 直答模型名（`zhida-*`） |
| `ZHIHU_GAME_QUOTA_ZHIDA` | 建议 `400` | NPC 高频对话限额 |
| `PORT` | 平台注入 | `run.py` 读取 |
| `TURN_URL` / `TURN_USER` / `TURN_PASS` | 可选 | 不配则语音只给公共 STUN，跨网可能连不上 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 可选 | 自建 OpenAI 兼容通道 |
| `ZHIHU_OAUTH_*` | 可选 | 当前 `.env` 未走 OAuth，不需要 |

`.env` 已被 `game/.gitignore` 与根 `.gitignore` 双重忽略，且 `.dockerignore` 排除 —— 凭证不会进镜像/仓库。

## 七、已知坑（都是实跑踩出来的）

1. **`render.yaml` 的 `dockerfilePath` 曾写成 `./Dockerfile`** —— Render 的 `dockerfilePath` 与
   `dockerContext` **都相对仓库根**解析，而 Dockerfile 在 `game/` 下，照原样部署必然构建失败。已修为 `./game/Dockerfile`。
2. **`msiexec` 遇到中文路径报 `rc 1639`**（Invalid command line argument）——
   解包 MSI 到 `D:\Vibe coding\知乎黑客松\...` 一直失败，换纯 ASCII 路径（`%TEMP%\cfx`）立即成功。
3. **大文件下载会被中途截断** —— 之前拉 `cloudflared.exe` 得到 19.2MB 残片，
   PE 头完整但 `.rdata`/`.reloc` 等 section 全截断，报 `Exec format error`，
   极易误判成"沙箱不让执行"。用 `tools/bin/_fetch_cloudflared.py`（分块续传 + PE 结构校验）或
   `winget download`（走 Microsoft 通道，带哈希校验）才可靠。**正确的 exe 是 52.4MB**。
4. **`agents/cache` 未挂持久卷**（`render.yaml` 只挂了 `/app/data`）——
   `LLMCache`/`DailyBudget` 有 `OSError` 兜底会退化成纯内存，不致命，但重启丢额度统计。要保留就加挂一行。
5. **隧道地址不要用正则随便抓**：cloudflared 日志里同时有 `https://api.trycloudflare.com`（控制面端点），
   不加负向断言会把 API 端点当成隧道地址，自检直接 405。

## 八、实测记录（2026-09-14）

| 项目 | 结果 |
|---|---|
| 本地 `/api/health` | 200，`engine: engine_v3 available` |
| 隧道公网 `POST /api/session` | 200，返回 `{ok, session:{session_id: s_..., engine: engine_v3}}` |
| 隧道公网 `WSS /ws/{sid}` | **握手成功，首帧 `system/snapshot stage=break_ice`**（REST+WS 全链路通） |
| cloudflared 隧道稳定性 | 5 次探测 **3 次 200**，TLS 握手 0.6~1.5s |
| serveo 隧道 | HTTP/WSS 全通，但**首屏是 `Serveo - Warning` 警告页**（浏览器实测） |
| 域名可达性对照 | `onrender.com` 301 ✅ / `dashboard.render.com` 200 ✅ / `github.com` 超时 ❌ / `render.com` 超时 ❌ |

**结论**：技术上"免费上线"已跑通并可复现；但本机网络对境外服务干扰明显，
所以**演示场景用隧道（延迟低、无需账号），长期公开链接用 Render 或国内服务器**。

## 九、上线前检查清单

- [ ] `.env` 完整，且 `git status` 里看不到 `.env`
- [ ] `curl https://<域名>/api/health` 返回 200 且 `engine.available = true`
- [ ] 浏览器打开后 F12 确认 WebSocket 返回 **101**（不是 400/404）
- [ ] `data/` 已挂持久卷（否则重启丢档）
- [ ] 实例数 = 1
- [ ] `proxy_read_timeout` > 30s
