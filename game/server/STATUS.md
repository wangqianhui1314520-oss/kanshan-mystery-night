# server/ 状态报告（F 服务端组）

## 2026-09-14：NPC 社交前后端接线复核

- 圆桌 DM 面板新增“请 AI 角色依次发言”；单人/多人圆桌私聊目标包含 AI，已由真人扮演的角色不列为 AI。
- `Store.npcWhisper` / `requestNpcWave` 已连接实际 HTTP 路由；等待状态、失败提示、发送失败保留输入、HTTP/WS 消息去重和全桌发言可见性已接入。
- `server/npc_social.py` 统一处理私聊与波次：读取当前 API 配置、引擎记忆版本、阶段闭卷与一致性守卫；校验入座玩家、真人占用席位和结束状态；私聊记忆与公共 NPC 短期记忆分开，公共会话响应剔除私聊数据。当前信任参数仍为保守的 0，未实现动态信任关系系统。
- 验证：`python -m pytest -q -p no:cacheprovider game/tests/test_npc_social.py game/tests/test_chat_replies.py` 14 项通过；`node game/tools/test_npc_social_frontend.cjs` 前端逻辑验证通过。测试使用确定性 Provider，不代表真实模型质量验证或浏览器视觉验收。
- 本机 HTTP 检查：8000 提供当前前端和新路由；8899 前端已更新但后端进程没有新路由，需重启该服务。未停止现有对局进程。
- 第二/三幕新增设计仍以 `ACT2_ACT3_OPTIMIZATION.md` 为方案，不能据此宣称新机制已实现。AI 自由社交/实时语音仍未完整闭环。

> 完成时间：2026-09-12 · 契约基线：docs/CONTRACTS.md §3.6/§3.7 + docs/ASSETS_INVENTORY.md 额度纪律
> 状态：**F 完成** —— 全部路由联通，curl/WS 实测取证，mock 状态机可开关

## 一、交付物（全部在 server/ 权限内）

| 文件 | 内容 |
|---|---|
| `main.py` | FastAPI 入口：§3.7 五条路由 + §3.6 事件协议 + WS 房间 + 中间件装配。`GameServer` 保留骨架签名（`__init__/on_connect/handle`），`handle` 现已实现路由 |
| `gateway/zhihu_gateway.py` | 知乎 API 网关：免鉴权直调（盐言/知识）+ 鉴权（热榜/搜索/直答）+ 磁盘缓存 + 节流单飞锁 + 话题白名单 + 真实降级信封。遗留签名 `chat/load_scenario/_quota_ok/_count/_fallback/_read_cache/_write_cache` 全部保留 |
| `store/session_store.py` | JSON 持久化（原子写 tmp+replace）：会话存档 + 长期记忆；签名保留，增量 `list_sessions/delete_session/append_event/exists`；ID 白名单校验防路径穿越 |
| `safety.py` | 内容安全过滤：政治敏感/违法暴恐/色情赌博/真实隐私（手机号·身份证·银行卡）拦截；`ContentSafetyMiddleware`（REST）+ WS 显式检查 + 出站 sanitize |
| `mock_engine.py` | 可开关 mock 状态机（`ZHIHU_GAME_USE_MOCK_ENGINE`，默认开）：阶段序列与 `engine/stage_machine.py` Stage 枚举一致（break_ice→investigate→round_table→accuse→review）；事件严格按 §3.6；自动加载 D 窗口 `content/scenarios/kanshan/`（scenario.json 角色卡 + clues/ 32 条真实线索，缺失时回退内置 mock 池） |

## 二、路由与协议（冻结，未改）

```
POST /api/session             创建对局（mode=main|daily|quick）
GET  /api/session/{id}        对局状态
POST /api/session/{id}/action 统一动作（search/chat/skill/counsel/vote/advance）
WS   /ws/{session_id}         事件流（快照 → 双向 §3.6）
GET  /api/health              健康检查（含 API 降级状态）
```

- 事件信封：`{"type","session_id","round","actor","payload"}`；client→server 仅限 §3.6 六类型，违规回 `system/error` 真实原因。
- REST 动作结果：`{"ok": true, "events": [...], "session": 快照}`，事件同时广播进 WS 房间（REST/WS 同管线）。

## 三、额度与降级纪律（硬规则落实）

| 能力 | 鉴权 | 额度（env 可覆盖） | 缓存 | 失败行为 |
|---|---|---|---|---|
| 盐言故事/知乎知识 | 免鉴权直调 | 无 | 永久 | 信封 `ok:false, source:fallback, degraded:true` + 真实原因，不伪造正文 |
| 热榜 | Bearer ZHIHU_ACCESS_SECRET | **2/日** | 按天全服共享 | 同上 + 话题白名单过滤（非白名单标题剔除并计数） |
| 知乎搜索/全网搜索 | 同上 | **10/日** | 按归一化问题永久 | 白名单外查询直接拒绝（**不消耗额度**） |
| 直答 | 同上 | **2/日** | 按问题永久 | 兜底文本明确标注「非真实生成内容」 |

- 凭证仅读环境变量 `ZHIHU_ACCESS_SECRET`（Bearer + 秒级 X-Request-Timestamp），不落代码/前端/文档。
- 配额计数持久化 `data/cache/quotas.json`，重启不涨额度；单飞锁（同一时刻仅 1 个真实调用）+ 最小间隔节流（默认 1s）。
- 降级信封统一：`{"ok","source":"api|cache|fallback|rejected","degraded","notice","data"}`。

## 四、实测证据（2026-09-12，uvicorn @ 127.0.0.1:8899）

1. **GET /api/health** → `{"status":"ok","engine":{"mode":"mock",...},"gateway":{...额度/白名单/最近错误...},"degraded":true}`（degraded=true 因本进程未导出 ZHIHU_ACCESS_SECRET——如实上报，凭证在 keychain，起服时 `ZHIHU_ACCESS_SECRET=xxx` 注入即转 false）。
2. **POST /api/session**（mode=main）→ `s_20260912_0001/0002`，8 NPC、AP=4、阶段「破冰·初到档案局」。
3. **POST action** `advance` → 进入 investigate（round 2，AP 12）；`search` → `clue_gained`（clue_mock_001 被擦掉的监控片段，payload 带 `mock:true`）+ `danmaku`；`chat` → `chat` 事件（actor `npc:char_04`，mock 模板台词）。
4. **WS /ws/{id}** → snapshot（stage/round/engine）→ ping/pong → 客户端发 `chat` 收到 `chat`+`danmaku` 广播 → 发非法类型 `hacked` 收 `system/error`（契约 §3.6 白名单提示）→ WS 消息含手机号被内容安全拦截。
5. **内容安全中间件（REST）**：POST 带 `13812345678` → HTTP 422 `content_blocked`，动作未执行、未耗额度。
6. **网关真实网络取证**：`story_list()` 直调 api.zhihu.com 成功（source=api，20 条）；无凭证时 hot_list/search 返回 `degraded:true` + 真实原因；白名单外查询 `rejected` 不耗额度。
7. **投票结算**：单玩家投 char_02（pollution 阵营）→ `vote`+`ending`（accused=npc:char_02，outcome=truth_win），status=ended 落盘；已结束对局再动作被诚实拒绝。
8. **持久化**：`data/sessions/s_20260912_0001~0004.json` 均可回读（原子写 + 损坏容错）。

## 五、运行方式

```bash
cd game
# 可选注入凭证（热榜/搜索/直答需要；盐言/知识免鉴权）
ZHIHU_ACCESS_SECRET=<你的secret> python -m uvicorn server.main:app --host 127.0.0.1 --port 8899
```

环境变量（全部可选）：`ZHIHU_ACCESS_SECRET`、`ZHIHU_GAME_USE_MOCK_ENGINE`（=0 关 mock 等 B 窗口引擎）、`ZHIHU_GAME_QUOTA_ZHIDA/SEARCH/GSEARCH/HOT`（默认 2/10/10/2）、`ZHIHU_GAME_TOPIC_WHITELIST`（逗号分隔，`*` 放行全部）、`ZHIHU_GAME_THROTTLE_SECONDS`（默认 1）、`ZHIHU_GAME_OPEN_API_BASE`、`ZHIHU_GAME_CONTENT_API_BASE`、`ZHIHU_GAME_HTTP_TIMEOUT`。

## 六、集成接缝（给 B/C/E 窗口）

- **B（引擎）**：mock 与引擎的切换点在 `GameServer.run_action`——B 提供 `apply_action(session, type, actor, payload) -> (events, error)` 同签名实现即可平替；阶段/AP 口径与 `engine/stage_machine.py` 对齐。关闭开关：`ZHIHU_GAME_USE_MOCK_ENGINE=0`。
- **C（Agent）**：网关遗留同步入口 `gateway.chat(system, user) -> str` 与异步 `direct_answer/search/hot_list` 可直接复用；降级时返回标注文本/信封，不伪造。
- **E（前端）**：WS 首条 `system/snapshot` 含 stage/round/heat/players/clues_gained 可直接渲染；REST 动作响应含完整事件列表可补帧；错误统一 `system/error` 或 HTTP 4xx + `detail`。

## 七、已知边界（如实）

- 服务器进程未注入 `ZHIHU_ACCESS_SECRET` 时鉴权能力降级（health 如实上报 degraded=true）；额度建议建队补贴到账后核对提额。
- mock 事件 payload 全部带 `mock:true` 与说明——演示可跑通，正式叙事以引擎+D 内容为准。
- 阶段推进为线性单轮（mock 简化）；三幕多轮、地点热度、双结局矩阵等由 B 引擎接管后生效。

## 八、自检报告（2026-09-12 · identify → fix → verify → mutation test → regression guard）

探针脚本：`server/_selfcheck.py`（可重复执行，32 项断言，覆盖正向链 9 项 + 负路径 23 项）。

**初跑 29/31 → 定位并修复 4 处：**

| # | 问题（identify） | 修复（fix） | 验证（verify） |
|---|---|---|---|
| 1 | mock 阶段白名单落后：counsel/skill 未纳入 investigate/round_table（B 引擎 `_STAGE_ACTIONS` 已升级，mock 未对齐） | `mock_engine.STAGE_ACTIONS` 对齐引擎权威表 | A5 counsel 匹配→memory_unlock ✓；A7 skill ✓ |
| 2 | 网关缓存命中路径不清理 `last_errors`——此前真实失败过的能力在有缓存后 health 仍误报 degraded | cache 命中时 `last_errors.pop(kind)` | B18 二次请求 source=cache ✓ |
| 3 | `_do_advance` 对非法 stage 值会 ValueError→500 | 非法值防御回退 idx=0 | 编译+回归 ✓ |
| 4 | WS 收到二进制帧时 `receive_text` 抛未捕获异常，死连接残留房间 | WS 循环兜底 except 诚实断开 | 回归 ✓ |

**负路径取证（B 系列，全部真实返回）：** 非法 mode→400；未知 session→404（REST+WS 4404）；契约外类型 `accuse`→400+§3.6 提示；payload 非对象→400；非法 JSON→400；政治敏感/身份证→422 content_blocked；AP=0 后动作→400 行动力不足；线索池抽干→`search_empty` 诚实提示不伪造；路径穿越 `../../evil`→ValueError/None；损坏存档→None 不崩；网关：二次拉取 source=cache、非法 work_id→rejected、白名单外搜索→rejected（不耗额度）、无凭证 hot→degraded+真实原因、直答兜底文本明确标注"非真实生成内容"。

**Mutation test 证据：** 将 investigate 白名单回退为旧版（移除 counsel/skill）后重跑探针 → **FAIL A5/A6/A7 立即触发**（连锁 A8b/A9），证明探针能真实捕获该缺口；恢复代码后 32/32 全绿（regression guard 通过）。探针本身亦经加固：动作返回错误时优雅 FAIL 不崩溃。

**终态：32/32 PASS**（正向 A1-A9 + 负路径 B1-B22，含 WS 双向、内容安全、持久化、网关降级链）。

## 九、B 引擎接线（2026-09-12 · engine_v3 已上线为默认通道）

B 窗口交付 engine/ 七模块后，F 完成 `server/engine_driver.py` 适配层接线（engine/ 只读导入，零改动）。

**适配层职责：**
- 与 mock 同签名（`create_session` / `apply_action`），`main.run_action` 按 session["engine"] 字段路由（老 mock 档继续可玩，新档走引擎）；
- 全局开关 `ZHIHU_GAME_USE_MOCK_ENGINE`：默认 0=引擎；=1 回退 mock（双向已回归验证）；
- B 要求的 F 侧联动全部落地：`EvidenceChain.sync_context(memory_versions/counsel_cards/chat_keywords/review_flags)`、`OpinionFeed.attach_knowledge`、`StageMachine.session_id` 回填、chat:keyword_ 对话框触发线索（clue_031「看山，关门」实测触发）、review:credits 复盘线索（终局时解锁）；
- 动作映射与 AP（resolver 口径）：search=1 / counsel=2 / skill=1（refute·buy_heat·memory_fix=2）/ chat·vote·advance=0；动作合法性单一事实源=引擎 `StageMachine.can()`；
- D 内容结构适配：location 双口径（scene_map key 英文 id ⇄ 线索中文名）；acts 为独立幕结构（break_ice/investigate/round_table/accuse）→ advance=幕线性推进（rounds_per_act 轮循环语义保留，内容无此结构时自动切换）；
- 会话恢复：session["actions"] 记录成功动作序列，服务重启后按固定 seed 回放重建引擎实例（引擎全确定性裁决，回放无膨胀已验证）；
- NPC 演出诚实占位：chat 产出 `system/npc_pending`（C 组 llm_client 接入点），不伪造 AI 台词。

**引擎 E2E 实测（REST 全链路，`server/_e2e_engine.py`，P1 12/12 + P2 1/1）：**
- E1 建局 engine_v3（32 线索池/8 角色）→ E2 advance→investigate(AP12) → E3 搜证「看山工位×鱼干」命中 clue_028（boss_flaw）+flaw_progress+抽卡 → E4 chat「看山，关门」触发 clue_031 → E5-E6 心晴抽卡（kc_01）+counsel 心病匹配命中（char_06，effect=boss_key，引擎真实裁决）→ E7 辟谣 refute（hotfeed_refresh）→ E8 买热搜 → E9 幕线性推进 4 幕到 accuse → E10 终局 vote 指认 DM（破绽 2/5）→ 引擎真实裁决 **dm_mock 群嘲结局**（「你连 DM 都想锤?」）→ E11 ended 后动作诚实 400 → E12 服务重启后 actions 日志回放重建、动作连续（acts 2→3 / clues 1→2 / AP 11→10 单调无膨胀）。
- mock 回退通道回归：`ZHIHU_GAME_USE_MOCK_ENGINE=1` 下 selfcheck 32/32 全过（双向开关验证）。

**接线过程发现并处理：**
1. D 线索 location 为中文名、scene_map key 为英文 id → 适配层双口径映射（发现于 E3 首跑 FAIL）；
2. D acts 与 B 轮循环假设错位（round_table 独立幕）→ 适配层按内容结构自动选择推进语义（发现于 E9 首跑 FAIL）；
3. **多窗口并发事故**：B 对 engine/memory_system.py 的编辑中间态（缩进断裂）曾致服务重启 import 失败 → main.py 引擎导入容错加固（`_ENGINE_IMPORT_ERROR` 如实上报，health 标注 engine.error，建局/动作 503+真实原因+mock 回退指引），单窗口中间态不再拖垮服务；B 修复后自动恢复。
4. 本机系统代理会拦截 localhost 请求（curl/httpx 均中招，"upstream connect failed"）→ 探针脚本统一 `trust_env=False`。

**给 C/E 的接线点（引擎模式下已生效）：**
- C：chat 的 `system/npc_pending` 事件即演出挂载点；`MemorySystem.visible_blocks(char_id, include_heart=解锁后)` 数据已在引擎内就绪；counsel 的 `transcript_hint` 已随 counsel_result 事件下发；
- E：终局后 `ending.payload.detail.review_clues` 为复盘页彩蛋线索；`boss_ready` 事件为「指认：DM」按钮显隐信号；hotfeed_refresh 携带完整面板。

## 十、MEGA_MODE 接线（2026-09-12 · 契约 v2.1 增量路由全通）

依据：docs/MEGA_MODE.md + 契约 v2.1 §3.7（login/profile/assets/party 均为契约已广播增量）。新增 `server/oauth.py`。

**1. 知乎身份系统（OAuth 交换 + 隐私三件套）**
- `POST /api/session/{id}/login`：authorization_code（兼容 code）→ `POST openapi.zhihu.com/access_token`（form 交换，成功以响应含 access_token 为准，code:20000 仅表示成功）→ `GET openapi.zhihu.com/user`（Bearer ZHIHU_ACCESS_SECRET + X-OAuth-Token + 秒级时间戳）→ **公开三件套+uid**（fullname/headline/avatar_path/uid）；email/phone_no 等字段**取回即丢弃**；
- 事件 `login_success` + `dossier_ready`（《求真档案局特聘侦探证》：编号=uid 后 6 位、警衔=headline 关键词欢乐花名——确定性占位，C 组 AI 个性化生成接入点已标注）；
- **隐私铁律**：OAuth token 仅存进程内存 `GameServer.oauth_tokens`（不落盘/不回传前端/不进日志）；三件套缓存在 session 内（`/api/profile/me` 优先读缓存，避免重复烧用户数据 API）；凭证仅环境变量 `ZHIHU_OAUTH_APP_ID/ZHIHU_OAUTH_APP_KEY/ZHIHU_OAUTH_REDIRECT_URI`（App Key 只后端）；
- 无凭证/假码 → 502 真实降级（不伪造登录态）；诊断信息只出长度+SHA-256 短前缀；`GET /api/profile/me` 未登录时回传 `authorize_url` 构建参数指引。

**2. party 多人同场**
- `mode=party` 建局自动生成 6 位房间码 + max_players（2-5，默认 5）；`POST /api/session/{id}/join`（房间码校验 403 / 房满 409+观战指引 / 重连自动取消 AI 接管）；
- **真人私聊**：`POST /api/session/{id}/whisper` → 以契约 `chat` 事件（payload.whisper=true）**定向投递**双方 WS（`broadcast_to`），不经 NPC、不触发引擎结算；留档 session 供复盘审计；目标须为真人（400）/ 内容安全 422 / 目标离线如实报 delivered=false；
- **AI NPC 私聊**：`POST /api/session/{id}/npc-whisper` → 调用 `AgentRuntime.npc_chat`，继承 NPC 人设/信任度/双层记忆/一致性守卫；不消耗 AP，事件仅定向返回发送者并写入 session；目标必须是已装载 NPC，内容安全失败 422，Agent 不可用返回 503。
- **NPC 主动波次**：`POST /api/session/{id}/npc-wave` → 让已装载 NPC 依次主动发言，事件带 `wave=true` 并广播全房间；适用于 DM 轮流介绍、幕转场和冷场救场，不改变 AP 或引擎裁决。
- **掉线 AI 接管**：WS 断连且该玩家无其他在线连接 → `system/ai_takeover` 广播 + session["ai_takeover"] 标记（C 组按此注入 AI 台词，口风一致性归一致性守卫）；
- **观战**：WS `?spectator=1` → 快照标记 spectator + 只读拦截（发动作回真实原因），人数不限。

**3. 静态资产路由**
- `GET /assets/*` ← `content/assets/`（StaticFiles 挂载，启动时目录自动创建）；实测 `assets/images/card_back.png` 返回 200 + `image/png`；前端所有图片/视频从此取（契约：禁止外链）。

**MEGA E2E 实测（`server/_e2e_mega.py`，17/17 PASS）**：assets 真实资产 200+image、party 房间码/错误码 403/join/观战/房满 409、whisper 定向投递（目标 WS 实收 chat 事件）+目标校验 400+内容安全 422、health 含 oauth 状态、login 无凭证真实降级、/profile/me 未登录指引、观战快照+只读拦截、掉线 ai_takeover 广播+落 session。回归：引擎链路 12/12 零破坏；mock 通道 32/32（STATUS §八）。

**接线事故（已修复）**：GameServer 曾存在**同名方法重复定义**（旧 on_connect/broadcast/handle 组未随 MEGA 改造删除，Python 后定义静默覆盖新定义）→ party 私聊 KeyError；已去重并以「方法名唯一性检查」作为回归步骤。多轮 Edit 追加方法时的教训：插入新方法前先确认旧方法组已整体移除。

## 十一、V31 增量（2026-09-12 · PartyBoard/DifficultyDirector/minis 全通）

依据：docs/GAMEPLAY_V31.md §9.4 + engine/STATUS.md §六（B 组 V31 5/5 交付）。改动：`engine_driver.py`（PartyBoard/DifficultyDirector 接线）+ `main.py`（minis 双路由/join 升级/掉线口径/脱敏视图）。

**1. party 引擎接线（engine/party.py · PartyBoard）**
- `join` 路由升级：真人入座走 `PartyBoard.join_seat()`（自动空位或 `char_id` 认领/顶替 AI 席），首个入座触发**阵营暗置发牌**（≤3 人局污染 2 / 4-5 人局 3，swayable 优先为被裹挟者——以上全部引擎内部裁决）；
- **faction 零透出三道闸**：① 席位视图 `seats_public()` 仅含 char_id/player_id/connected/ai_takeover/is_ai；② `GET /api/session` 剥离 `party` 快照键（暗置发牌数据仅存服务端档）且 party 模式 players 项剔除 faction 字段；③ `ai_takeover` 事件 notice 统一为「该角色已由 AI 接管」（不透玩家 id 与阵营），实测事件 JSON 中 pollution/truth 零出现；
- **多人 AP 各算各的**：party 模式真人动作走 `PartyBoard.spend()`（每轮 3 点/人，AI 席 `ai:char_xx` 同池由 C 组消费），非 party 模式保持幕配额池；`ap_state` 随 session 快照下发；
- 掉线：WS 断连 → `PartyBoard.leave()`（席位保留 + ai_takeover 标记）→ 广播 + 落 session；
- 回放重建：session["party"]=PartyBoard.snapshot() 随动作落盘，服务重启 `restore()` 后状态连续。

**2. 动态难度 + 轮次注入（engine/difficulty.py + knowledge_cards.set_round）**
- `create_session` 与每次进入 investigate 轮 → **`ks.set_round(n)` 注入**（急诊红灯「下一轮内双倍收益」有效期判定依赖此调用）+ `PartyBoard.reset_round_ap()`；
- 幕切换 → `DifficultyDirector.on_act_settled(metrics)`（线索数/覆盖率确定性规则 → assist/normal/hard）+ `apply(ec, of)` 落地（建议关键词数/热度阈值/ boss 宽限）→ `system/difficulty_set` 事件（只报「梯度已调整」，不泄底）；
- 搜证未命中 → `memo_for` 防卡死「档案局备忘录」（点方向不泄底，预算内）。

**3. minis 只读双路由（GAMEPLAY_V31 §9.4 架构约定 3）**
- `GET /api/minis/memory-puzzle?char=`：脱敏记忆池随机抽一题——**仅 said 层乱序输出**（id/time/text），heart 心声层零透出、引擎权威答案（puzzle_answer）不透；
- `GET /api/minis/hotfeed-pool?n=`：帖池脱敏抽样——`is_fake`/`clue_ref` 零透出（辨别是玩法、线索关联是主案），author_mask 已脱敏字段原样；
- 免鉴权 / 零额度（不调任何外部 API）/ 可缓存（`Cache-Control: public, max-age=300`）；数据源为 lifespan 装载的独立只读 MemorySystem/OpinionFeed（与对局引擎状态零耦合）。

**4. /assets/***：上轮已挂载，本轮复测 `assets/images/card_back.png` → 200 `image/png` ✓。

**V31 E2E 实测（`server/_e2e_v31.py`，11/11 PASS）**：minis 双路由 200+缓存头+脱敏字段审计、join→PartyBoard 席位（无 faction）、GET session 零暗置阵营、party AP 各算各的（player:1=2 / player:2=3 / AI 席各 3）、counsel 引擎裁决、ai_takeover 新口径（notice 逐字等于「该角色已由 AI 接管」且事件全文无 pollution/truth）、PartyBoard.ai_takeover 落席位、幕切换 difficulty_set。回归：engine P1 12/12 + MEGA 17/17 零破坏。

## 十二、memory-puzzle tier=open 过滤（2026-09-12 · 总控指令落地）

`GET /api/minis/memory-puzzle` 抽样口径收紧为 **M2 tier=open 过滤**：

- **显式标注优先**：块带 `tier=="open"` 直接入池；`tier` 为其他值（hidden/case 等）→ 永不入池；
- **存量降级口径**：当前 D 的 24 份 memory 文件块均无 tier 字段（实测 tiers={None}）→ 按 open 等效规则放行：said 层 + `integrity=original` + 文本不含案情敏感词（词表**只读复用** `engine.memory_system._BROADCAST_BLOCK_WORDS`，与引擎心声广播白名单同源不漂移）；D 未来标注 tier 后自动收敛为纯 open 池；
- 响应新增 `filter: {mode, pool_size}`（如 `open-equivalent (no tier tag: said+original+case-word-free)`），空池诚实 503 并提示等待 D 标注；
- 装载方式改为直读 memory/*.json 原始块（MemoryBlock dataclass 不携带 tier，引擎对象无法过滤）；heart 层 / edited·deleted 篡改块 / puzzle_answer 权威答案仍零透出。

**实测（6 次随机抽取跨 5 角色全量审计）**：案情词泄露 0、字段集恒为 {id,time,text}、heart-in-data=False；池量 char_01=4 / char_02=7 / char_03=5 / char_04=1 / char_05=7 / char_06=10 / char_07=6 / char_08=9（共 49 块）；未知角色 404 + 有池角色指引；V31 套件 11/11、engine 12/12、MEGA 17/17 全回归通过。

## 十三、AgentRuntime 演出层接线（2026-09-12 · 契约 §3.5c 落地）

依据 A 组广播：「server 持有 AgentRuntime 实例（agents/bridge.py），外部事件走 rt.record_event，终局走 rt.achievements_flow(ending_key) / report_flow，收集/头条/广播事故走对应 *_flow，与 engine_driver 并存（driver 裁决、rt 演出）」。改动仅 main.py（agents/ 只读，零改动）。

**接线面（并存架构）：**
- **持有**：`GameServer.runtimes`（session_id → AgentRuntime 懒构建 + 事件流回喂计数，成就判定素材跨重启连续）；导入容错同引擎（agents/ 中间态不拖垮服务，rt 路由 503+真实原因）；
- **外部事件记账**：driver 裁决事件实时翻译为 `rt.record_event`（clue_gained→search/hit_count、env_clue、counsel matched→heart_unlock_count、refute ok→fake_exposed/refute_success_streak、ending→endings 集），记账失败静默不影响裁决广播；
- **rt skill 分流**：`skill=collect` → `rt.collect_flow`（CollectiblesBoard 自有裁决，拾取计数/重复拾取诚实拒绝）；`skill=bid_headline` → `rt.headline_flow`（rt.opinion 明牌竞标裁决 + 主持/结果演出；faction 取自 PartyBoard.faction_of 仅内部使用，事件零透出）；
- **终局流**：ending 事件 → `rt.achievements_flow(outcome)`（AchievementEngine 确定性判定，空结果发 `achievements_checked` 审计事件）→ `achievement_unlocked` 事件（兼容 dict/str 演出形态）→ `rt.report_flow` → `system/detective_report`（report_text + badges + achievements，前端分享卡素材，只导出图片不自动发布）；
- **心声广播事故**（P1）：advance 进入新轮 30% 概率 → `rt.broadcast_accident_flow`（rt.memory 白名单过滤：未解锁心声时 DM 诚实播报「暂无料可播」）→ `system/broadcast_accident`；
- **额度纪律**：rt 的 LLM 走 C Provider 链（LLM_API_KEY→zhida→mock 离线回放）——当前无 key 自动 mock 演出（确定性台词库），零额度消耗。

**rt E2E 实测（`server/_e2e_rt.py`，10/10 PASS）**：bake 素材产出、collect 拾取+1/重复拒绝、bid_headline 竞标结算（faction 零透出）、幂等复用、终局 detective_report 生成（report_text/badges/achievements 结构合规）、achievements_checked 审计、演出链贯通。全量回归：V31 11/11 + engine P1 12/12 + MEGA 17/17 零破坏。

**边界说明（如实）**：rt 内部引擎镜像与 driver 引擎为两套对象（A 组「并存」设计），深度状态（rt.evidence 破绽/释放集）不与 driver 实时同步——成就判定素材以 record_event 喂入的计数为准；喂入键清单见 `_feed_rt_event`。C 组若需引擎深度状态，应经 rt 自身方法（sync_flaws/unlock_memory）由 F 在裁决点显式调用（当前接线：演出前不额外调用，避免双写副作用）。

## 十四、C 组交代对接（2026-09-12 · 暗拍/拼图/深状态同步）

依据 C 组交代：「PartyBoard.from_roster 已在 bridge 内构造（faction 仅内部使用不透出前端）；暗拍 2AP 与拼图篡改点成本由上层在调用前扣减/校验（拼图不足时 flow 返回 not_enough_tamper_points，无需预扣）」。

**1. 暗拍（P2）**：`skill=stealth_photo` → 上层 `_spend_ap()` 校验并扣 **2AP**（party 走 PartyBoard 池各算各的 / 单人 engine 档走幕配额池 / mock 档走 session 计数）→ `rt.stealth_photo_flow(location, keyword)`；location 双口径映射（scene_map key→线索中文名）与搜证一致。实测：12→10AP、照片持有（photo_id 结构）、未命中时「行动力已扣」如实提示。

**2. 记忆拼图对质（P2）**：`skill=puzzle` → `rt.puzzle_flow(char_id, proposal)`；篡改点成本（2 个）由 **flow 内部校验**（不足 → `puzzle_rejected` 事件 +「先通过记忆修复/知识开导发现记忆出入」指引，无需预扣——实测 C3）；**深状态同步**：driver 每次 `memory_unlock` 事件回喂 `rt.unlock_memory(char, reason)`——rt.memory 版本链/篡改点发现与 driver.ms 保持一致（实测 memory_fix×3 后拼图 flow 篡改点就位、判定产出排错锐评）。排对后的「全场获线索」奖励发放为 C/D 细化边界（事件 notice 已标注）。

**3. faction 零透出加固**：`headline_result` 事件的 bid/settle 引擎原样返回**含 faction 顶层字段**（B 引擎「明牌仅内部使用」）→ 白名单化剔除（settle 仅保留 ok/winner/post_id/topic），实测事件 JSON 零 faction 键。

**C-handover E2E（`server/_e2e_chandover.py`，7/7 PASS）**：暗拍 AP 扣减/照片持有/拼图不足诚实拒绝/回喂同步链/拼图判定/faction 零透出/无副作用续玩。全量回归：RT 10/10 + V31 11/11 + engine P1 12/12 + MEGA 17/17 零破坏。

## 十五、minis 数据源切换 rt 口径（2026-09-12 · C 组交代落地）

依据 C 组交代：「memory-puzzle 路由直接调 rt.memory_puzzle_pool(tier="open") 取题（免登录流量），登录局内热身关可用 tier="full" + rt.heart_quiz_flow() 判定与结算；未登录路径无需 session、无额度消耗」。

**改动**：
1. `GET /api/minis/memory-puzzle` 数据源切换为 **rt.memory_puzzle_pool(tier)**（segments_lib 题库：open 6 题 / full 4 题），退役直读 memory/*.json 的实现；lifespan 建独立 `minis_rt`（不进对局 runtime 缓存，免登录路径零 session 依赖、零额度）；
2. **题面白名单**：仅 `{npc, said, heart}`——`answer`（答案位）/`teaching`（结算教学点）服务端持有零透出；open 题的 heart 为 C 审核的无案情词彩蛋层数据（M2 玩法本体）；
3. **tier=full 仅登录局内**：要求 session_id + player_id 且 OAuth 登录缓存命中，未登录 403 真实拒绝；响应 no-store（open 才可缓存 max-age=300）；
4. 新增 `POST /api/minis/heart-quiz` 判定与结算：前端回传题面 → 服务端按 (npc, said) 反查题库原题（含答案位，防伪造/防抄答案）→ `rt.heart_quiz_flow(原题, answer)` → {correct, npc, teaching, show}（答完揭教学点）；full 题判定同样要求登录态；伪造题面 404。

**实测（MINIS-RT AUDIT PASS）**：open 取题 200（题面白名单 + 缓存头）、full 未登录 403、open 判定 200（correct 布尔 + show 演出 + teaching 揭示）、伪造题面 404；全量回归 RT 10/10 + V31 11/11 + engine 12/12 + MEGA 17/17 零破坏。

## 十六、G5 知乎能力接入（2026-09-12 · 官方 0.7.2 文档三能力入网关）

依据：zhihu-skill 官方文档 hackathon-user-profile-api.md / creator.md / hackathon-oauth.md / http-api.md + 契约 §3.7 + ASSETS_INVENTORY 额度纪律。**改动仅 `gateway/zhihu_gateway.py`**（main.py 零改动——`/api/profile/me` 核对为 F 已实现且字段口径合规）。

**1. `user_profile(access_token)`（用户数据组）**
- `GET openapi.zhihu.com/user`，鉴权仅 `Authorization: Bearer <OAuth access_token>`（官方 0.7.2：无需 Access Secret / X-OAuth-Token / 时间戳）；
- **隐私铁律**：只透出公开四字段 uid/fullname/headline/avatar_path——email/phone_no/phone **零读取**（不 get、不缓存、不落任何存储）；uid 按 int64 无损解析后转字符串传递；
- 响应处理按官方要求：不凭 HTTP 200 判成功，业务 code 校验 + uid 缺失即降级（不建立会话）；资料短缓存 300s（按 token SHA-256 指纹键，不存 token 本体）；额度 user 组网关保守 200/日（官方 1000/日，`ZHIHU_GAME_QUOTA_USER` 可覆盖），每日计数持久化；
- 实现方式：`_call` 增量 `extra_headers` 参数（OAuth Bearer 形态），既有单飞锁/节流/降级信封全部复用。

**2. `creator_stats(access_token, content_url, start_date?, end_date?)`（creator 额度组）**
- 官方 creator.md `me content-stats`：`GET /api/v1/user/creator_content_stats?ContentUrl=...`，Bearer Access Secret + 秒级时间戳；
- **`access_token` 参数按签名保留但被忽略**（官方文档：creator 四项只认 Access Secret 所属账号，X-OAuth-Token 不能切换身份）；
- content_url 白名单正则（answer/question-answer/pin/zvideo/zhuanlan p 五形态）；StartDate/EndDate 成对 + YYYY-MM-DD + 时序校验，违规 rejected 不耗额度；
- 业务码全处理（Code!=0 → 降级 + 真实 Message：10001/20001/30001/30002/30003/90001）；统计短缓存 600s。

**3. `question_recommend(query?, count=5)`（creator 额度组·择一实现）**
- 官方 http-api.md：`GET /api/v1/user/question_recommendations?Query=&Count=`；画像模式（不传 Query）/ 主题模式（Query 必填）双模式；Count 1-20 夹紧；
- 主题模式过**话题白名单闸门**（与 search 同口径，拦截不耗额度）；推荐结果按归一化 (query|count) **永久预生成缓存**（重复请求不重复烧额度）；
- 额度：creator 组共用——官方 100/日、未实名 10/日，网关保守取 **10/日** 硬编码（`ZHIHU_GAME_QUOTA_CREATOR` 可覆盖），每日计数持久化 quotas.json 重启不涨；`live_quota()` APIIDs 增补 creator。

**对齐核对（main.py 零改动）**：`/api/profile/me`（F 实现）走 `oauth.fetch_profile`，字段口径 = uid/fullname/headline/avatar_path 与契约 §3.7 一致，email/phone 取回即丢弃 ✓；`/api/health` 透出 `gateway.health()`，creator/user 两个新额度组自动入 quota_daily ✓。

**实测（2026-09-12，uvicorn @ 127.0.0.1:8907——8899/8901 被其他窗口进程占用）**：
- 自测脚本全路径：user_profile 空 token→rejected / 假 token 真实联通线上 openapi 返回业务 code=20005 → 降级不建立会话、**泄漏字段集=空** ✓；creator_stats 非法 URL/非法日期→rejected 不耗额度 ✓；question_recommend 白名单外→rejected、主题/画像模式无凭证→degraded 真实原因 ✓；
- curl /api/health → HTTP 200，`quota_daily` 含 `creator:{used:0,limit:10}` + `user:{used:0,limit:200}`，gateway 自身 degraded 空；
- curl /api/profile/me（存在 session、未登录）→ 真实降级信封 `{ok:false, notice:未完成 OAuth 登录指引, authorize_url:null}` 不伪造资料；
- 无凭证环境全部走降级信封 = 验收口径达成；凭证仅环境变量，零硬编码。

## 十七、G3 引擎编排 · V4 综艺阶段事件（2026-09-12 · 契约 §3.6 信封全确定性）

**改动仅 `server/engine_driver.py` + `engine/stage_machine.py`**（零 LLM，全部裁决确定性）。叠加于 A 窗口修复轮（G04/G06/G10/G11/G13 + 机制幕门控）之上，未回退任何修复。

**1. 新增 system 事件（payload 带 event 字段，§3.6 信封：type/session_id/round/actor/payload）**
- `case_intro`（建局后）：create_session 即产出，进 session["events"]（REST 响应与 WS 回放均可见）。数据源：标题/简介读 scenario.json（title/genre/summary）；**证物清单只收 public 层线索**（id/name/location 三字段，fact/linked_truth_nodes 零携带——零剧透确定性截取）；署名 attribution 读 truth.json（V4 §一②案件卷宗页数据源）。
- `act_transition`（幕切换时）：_do_advance 检测 current_act_no 前后变化即发，payload 带 act_no / act_name / act_brief（scenario acts 幕引言）与转场图 `/assets/images/act_t{min(act_no,3)}.png`（t1/t2/t3，幕4 钳制 t3）；紧随 stage_changed 之后，幕内轮切换（end_round）不触发。
- `first_vote`（圆桌幕结束时）：离开 round_table 幕的一次性非正式投票邀请（kind=informal / binding=false / poll_id=first_vote_{sid} / targets=8 NPC），会话级 `_first_vote_sent` 幂等，仅发一次——对应 V4 §一⑥「第一次指认·不影响结局，喂弹幕梗」。

**2. 机制幕门控保持**：_do_skill 的 ACT_NOW / act_now<2（破冰锁技能）逻辑原样保留，未动白名单与任何修复；实测破冰幕 skill 仍被拒（白名单层拒绝 + locked 门控双层保险）。

**3. stage_machine 只读辅助**：新增 `StageMachine.current_act_no()`（返回 `_index+1`，1 起），供 driver 幕切换检测/转场复用，兼作契约 §3.5c collect_flow 的 act_no 缺省口径；不改既有签名。

**冒烟实测（ALL_PASS）**：case_intro 恰一条（public 证物 7 条无剧透字段）；advance 幕线性推进逐幕产 act_transition（幕2/3/4，转场图与幕名正确）；first_vote 仅在圆桌幕结束时发一条且不重复；investigate 幕 truth_check 正常 heat_report（门控解锁）；current_act_no 1→2 正确。回归：test_engine_units / test_e2e 全绿；test_showtime / test_v4_acceptance 的 2 failed + 40 errors 均为 `agents/bridge.py:136 _inject_agent_docs` 缺失（G4 组进行中状态），与本次改动无关。

> 备注：任务口径「STATUS.md 追加 §八」因 §八 已被「自检报告」占用，按现有编号顺延追加为 §十七。
