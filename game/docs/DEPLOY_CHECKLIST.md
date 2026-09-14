# 部署与提交清单 ·《求真档案局 · 看山失踪夜》

> 供队长今晚照做的执行清单。**截止红线：2026-09-15 10:00，逾期不补交，所有步骤倒排完成。**

## 一、Render Blueprint 部署步骤

仓库根已备齐 `render.yaml` + `game/Dockerfile` + `game/.dockerignore`，可直接走 Blueprint 部署：

1. 登录 Render Dashboard → **New + → Blueprint**，选择本仓库（先完成第五节 push）；
2. Render 自动读取根目录 `render.yaml`，确认服务配置：
   - `runtime: docker`，服务名 `kanshan-game`；
   - `dockerContext: ./game`（构建上下文指向 game 子目录）；
   - `healthCheckPath: /api/health`；
   - 持久磁盘挂载 `/app/data`（1GB，会话与数据落盘）；
3. 部署前先在 **Environment** 面板填齐第二节的环境变量（缺 key 也能起服务，但 AI 回复会走降级提示，影响评委体验）；
4. 触发首次部署，等待健康检查通过（`/api/health` 返回 200）；
5. 记下分配的正式域名（如 `https://kanshan-game.onrender.com`），后续 OAuth 登记要用。

## 二、环境变量清单（只列键名，值绝不进镜像/仓库）

在 Render 控制台 **Environment** 面板逐项填写，与本地 `game/.env` 的键一一对应：

| 键名 | 用途 |
|---|---|
| `ZHIHU_ACCESS_SECRET` | 知乎开放平台凭证（核心，必填） |
| `ZHIHU_LLM_MODEL` | LLM 模型名 |
| `ZHIHU_GAME_MODEL` | 游戏内模型配置 |
| `ZHIHU_GAME_QUOTA_ZHIDA` | 直答调用限额 |
| `PLAYER_ACT_SLIM` | 演出瘦身开关 |

纪律：

- **只在 Render 环境变量面板填写，绝不写入 Dockerfile、render.yaml、前端代码或仓库任何文件**；
- 本地 `game/.env` 已确认在 `.gitignore` 覆盖范围内，push 前按第五节再复核一次；
- 凭证泄露 = 合规一票否决，填错值可在面板改后重新部署，不要回写到代码里。

## 三、OAuth 回调地址一致性检查

1. 正式域名确定后（第一节第 5 步），到知乎开放平台/活动页登记的回调地址必须**逐字符一致**：scheme、域名、端口、路径都不可差；
2. 本地开发用的 `http://localhost:...` 回调不得出现在生产登记里；
3. 部署后在 Demo 页实际走一遍"知乎登录 → 生成特聘侦探证"，确认回调不被 4xx/403 拦截；
4. 若域名有变（如自定义域名），同步改登记，再回到本条第 3 步复验。

## 四、部署后冒烟清单（按顺序，全绿才算部署完成）

- [ ] 打开首页，静态页返回 200，标题与署名正常渲染；
- [ ] `POST /api/session` 建局成功，返回会话 ID；
- [ ] 「开始调查 → 评委线」单人 20 分钟走通：破冰 → 搜证 → 圆桌 → 指认 → 复盘，无阻断性报错；
- [ ] 任一 NPC 对话回复带来源徽章且显示 **AI**（证明实时生成而非缓存/预写）；
- [ ] 降级场景演练：临时清空/填错 `ZHIHU_ACCESS_SECRET` 重新部署 → 回复区显示**真实降级提示**（不伪装 AI 生成、不漏后台故障词），验完改回正确值；
- [ ] `/api/health` 健康检查 200；
- [ ] 手机浏览器打开首页可正常进入（评委可能用手机看）。

## 五、git / 仓库步骤

本地仓库已初始化且基线已提交，`.env` 密钥未入库（已核验）。剩余动作：

1. **push 前最终复核**（必做，双保险）：
   ```bash
   git ls-files | grep -i env
   ```
   预期输出为空或仅命中 `.env.example`/`.gitignore` 这类无值文件；若出现 `game/.env` 立即停下排查；
2. 确认远程并推送（占位，替换为实际地址）：
   ```bash
   git remote add origin <GitHub 仓库地址>
   git push -u origin main
   # 备份二选一：
   git remote add gitee <Gitee 仓库地址>
   git push gitee main
   ```
3. push 成功后回到第一节做 Blueprint 部署；
4. 提交表单里附 GitHub/Gitee 链接与线上 Demo 链接（`SUBMISSION_产品说明.md` 顶部占位同步替换）。

## 六、截止时间红线

- **截止：2026-09-15 10:00，逾期不补交。**
- 建议倒排：今晚完成 push + Render 部署 + 冒烟全绿；明天上午留足缓冲只做报名表填写与链接核验，不做任何新改动。
- 部署或冒烟一旦在最后 2 小时内出问题：优先保「首页可开 + 评委线可玩」，其余问题记录进提交说明即可，不带病上新。
