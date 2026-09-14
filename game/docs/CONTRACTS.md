# 并行开发契约 v2（CONTRACTS）

> 多窗口并发开发的唯一协作依据。每个窗口只允许写自己"管辖目录"内的文件。
> 跨模块调用只走本文 schema 与 WS 事件协议；契约变更必须回 A 窗口（总控）并广播。
> v2 变更：接入 STORY_ADAPTATION / KNOWLEDGE_SYSTEM / DM_BOSS_DESIGN 三份设计——新增记忆双层、知识卡、舆论辟谣校验、Boss 层。

## 一、目录所有权（零冲突铁律，文件级）

| 目录 | 所有者 | 文件级说明 |
|---|---|---|
| `game/docs/` | A 总控 | 全部设计文档 |
| `game/schemas/` | A 总控 | 权威示例 JSON（各窗口只读） |
| `game/tools/` | A 总控 | asset_gen.py / asset_manifest.json / .env（不入库） |
| `game/engine/` | B 引擎组 | stage_machine / evidence_chain / timeline / resolver / **memory_system / opinion_feed / knowledge_cards / party / difficulty** |
| `game/agents/` | C Agent 组 | dm_agent / npc_agent / judge_agent / consistency_guard / **llm_client** / prompts/ |
| `game/content/scenarios/kanshan/` | D 内容组 | scenario.json / truth.json / timeline.json / characters/ / memory/ / clues/ / knowledge_cards/ / hotfeed/ / scripts/ |
| `game/studio/` | A 工作台 + S1 LLM 线 | 一句话生成快本：compiler/validate 属 A；`llm_steps.py` 属 S1。认约 `docs/STUDIO_WORKBENCH.md` |
| `game/content/scenarios/gen_*/` | 工作台运行时产物 | 只许 `gen_*`；禁止覆盖 kanshan/template |
| `game/content/worlds/` | A 已入库源文本 | yanyan_sources/（14 篇官方正文）——只读引用 |
| `game/content/assets/` | A 生成、D 选用 | images/ videos/（asset_gen.py 管线产出） |
| `game/frontend/` | E 前端组 | index.html / css / js / components |
| `game/server/` | F 服务端组 | main.py / gateway/ / store/ |
| `game/tests/` | G 测试组 | 全部测试 |
| 根目录共享 | A 总控 | README / requirements.txt / .gitignore / 部署配置 |

> engine/agents/server 的 .py 骨架由 A 预置（签名即契约）；实现与内部重构归各窗口，**不得改函数签名与返回结构**——要改回 A 广播。

## 二、窗口任务简报（开窗口整段粘贴）

| 窗口 | 定位 | 任务简报 |
|---|---|---|
| **A（本窗口）** | 总控/架构/集成 | 维护契约与设计文档；评审各窗口产出；端到端集成与提报材料 |
| **B** | 引擎组 | "读 docs/GAME_DESIGN_V3.md、STORY_ADAPTATION.md、KNOWLEDGE_SYSTEM.md、DM_BOSS_DESIGN.md 与本契约，实现 engine/ 七模块：stage_machine（三幕状态机+系统提示音事件）、evidence_chain（线索池/发卡/地点热度/证据合成/伪造）、timeline（轨迹一致性）、resolver（行动力/结局矩阵含 boss_layer 与指认 DM 分支）、memory_system（said/heart 双层记忆+篡改点+解锁）、opinion_feed（热度值/水军帖/辟谣卡校验）、knowledge_cards（10 卡池+心病匹配表+开导结算+辟谣弹药）。只写 engine/，输入输出按 schemas/，全部可离线单测。" |
| **C** | Agent 组 | "读同上四份设计+契约，实现 agents/：DM（刘看山伪装系统提示音人格，破绽计数注入，终极层现身演出）、NPC（双层记忆：heart 层仅在解锁后注入）、Judge（truth_node 覆盖度+心晴诊室结算）、一致性守卫（心声与口供矛盾拦截）、llm_client.py（Provider 抽象：直答 Agent=每日导读等低频高光 2 次/日，自建 LLM=主力对话，全量预生成缓存+降级）。Agent 无权改证据事实，只演不裁。" |
| **D** | 内容组 | "读四份设计+契约+schemas/，产出 content/scenarios/kanshan/：scenario.json（3 幕 11 地点）、8 角色卡（faction/秘密/目标）、memory/（V1-V3 双层 said/heart+删除段）、truth.json（表层+里层 Boss 层+5 破绽伏笔链）、clues/（32 条含伪造 6+破绽 5）、knowledge_cards/（10 卡：标题/作者/金句3/摘要/心病绑定）、hotfeed/（40+ 帖）、scripts/（三幕剧本+致敬台词埋点）。剧情按 STORY_ADAPTATION 缝合盐言三作，台词署名表随复盘页输出。" |
| **E** | 前端组 | "读契约事件协议+V3 搜证详设，实现 frontend/：Vue3 单页——场景图 11 地点、对话流、个人证物袋与知识卡图鉴、热搜面板、弹幕层、圆桌投票（含动态「指认：DM」按钮）、心晴诊室结算页、复盘页（含署名区与 Boss 揭示演出）。样式：深色档案局 HUD+知乎蓝，移动端适配。" |
| **F** | 服务端组 | "读契约，实现 server/：FastAPI+WebSocket 房间、session_store 持久化、gateway/zhihu_gateway.py（盐言/知识/热榜/直答：缓存、节流、降级、话题白名单）、内容安全过滤中间件。凭证仅环境变量。" |
| **G** | 测试组 | "建 tests/：引擎单测全覆盖、schema 校验、端到端一局（单人 8 NPC 三幕全流程）、阵营平衡模拟（污染/求真胜率 45-55%）、boss 触发链测试（5 破绽→指认 DM）、API 降级演练。" |

## 三、核心 Schema（权威定义）

### 3.1 角色卡 character.json
```json
{
  "id": "char_04", "name": "路人甲", "archetype": "匿名吃瓜群众",
  "faction": "truth | pollution | swayable",
  "public": { "avatar": "assets/images/char_lurenjia.png", "bio": "", "speech_style": "" },
  "secret": { "motive": "", "alibi": "", "guilt": "" },
  "goal": "个人任务（引擎校验）",
  "heartache": "kc_04",
  "memory_versions": ["memory/char_04_v1.json"],
  "deleted_segments": []
}
```

### 3.2 记忆版本 memory_version.json（双层）
```json
{
  "owner": "char_04", "version": 2,
  "blocks": [
    { "id": "blk_02", "time": "21:00", "layer": "said",
      "text": "我去茶水间泡面，看到流量酱神色慌张地跑过去。", "integrity": "edited" },
    { "id": "blk_02h", "time": "21:00", "layer": "heart",
      "text": "（心声）其实我 21 点半才到茶水间，刚才在偷偷补打卡……", "integrity": "original" }
  ],
  "diff_from_prev": [ { "block": "blk_02", "change": "时间 21:30→21:00，背影→流量酱", "tamper_point": "tp_02" } ]
}
```
> `layer: said | heart`；heart 层仅在「记忆修复/知识开导」解锁后注入 NPC prompt；篡改点=两层矛盾或版本 diff，由引擎自动转线索。

### 3.3 线索卡 clue.json
```json
{
  "id": "clue_007", "name": "被擦掉的监控片段",
  "tier": "public | limited | hidden | fake | boss_flaw",
  "location": "监控室", "tags": ["监控", "21点", "删除"],
  "fact": "客观事实（AI 不可改写）",
  "flavor_hint": "AI 扩写自由度提示",
  "linked_truth_nodes": ["tn_03"],
  "unlock_condition": "默认 | evidence:clue_003 | memory:char_04:3 | counsel:kc_06 | boss:flaw_count>=3",
  "fake_of": null, "flaw_id": null
}
```
> `boss_flaw` 级=看山破绽（flaw_id: flavor_1..5）；集齐 5 个解锁「指认：DM」。

### 3.4 知识卡 knowledge_card.json
```json
{
  "id": "kc_06", "work_id": "1697254818945699840",
  "title": "如何走出职业倦怠", "author": "草芽君Psy",
  "topic_tag": "倦怠",
  "golden_lines": ["金句1", "金句2", "金句3"],
  "summary": "100 字内摘要（卡背文案）",
  "binds": "char_06", "effect": "boss_key | evidence | memory_unlock | buff_ap | plot_fragment"
}
```
> 10 卡定义见 KNOWLEDGE_SYSTEM.md 心病匹配表；开导=消耗 2AP+卡匹配 binds → 成功演出+收益 / 失败群嘲演出。

### 3.5 热搜帖 hot_post.json
```json
{
  "id": "post_013", "round": 3, "title": "#谁动了我的鱼干#", "body": "…",
  "author_mask": "网友 | 水军 | 官方", "is_fake": false,
  "clue_ref": null, "topic_tag": "鱼干", "heat_delta": 8,
  "humor_tag": "一眼假但好笑 | 真线索伪装 | 玩梗"
}
```
> 辟谣=2AP+知识卡，卡 `topic_tag` 与帖匹配才生效；不匹配反涨热度（群嘲）。

### 3.6 WebSocket 事件协议
```json
{ "type": "search_result | chat | clue_gained | memory_unlock | counsel_result | hotfeed_refresh | faction_skill | vote | ending | danmaku | system",
  "session_id": "…", "round": 3, "actor": "player:1 | npc:char_04 | dm | kanshan", "payload": {} }
```
> client→server 仅 `search / chat / skill / counsel / vote / advance`；`actor: kanshan` = 终极层看山现身事件。

### 3.7 REST 路由
```
POST /api/session             创建对局（mode=main|daily|quick|party；可选 scenario_id，缺省 kanshan）
POST /api/studio/generate     一句话生成快本（认约 STUDIO_WORKBENCH §4）
GET  /api/studio              已生成本列表
GET  /api/studio/{id}         圣经+闸门（作者视图）
GET  /api/studio/{id}/public  试玩水合包（阵营/里层/guilt 零透出）
GET  /api/session/{id}        对局状态
POST /api/session/{id}/action 统一动作（search/chat/skill/counsel/vote/advance）
POST /api/session/{id}/login  OAuth code 换 token（party/个性化用）
GET  /api/profile/me          授权用户资料（uid/昵称/头像/headline，只取公开三件套）
WS   /ws/{session_id}         事件流
GET  /api/health              健康检查（含 API 降级状态）
GET  /assets/*                静态托管 content/assets/（前端所有图片/视频从此取，禁止外链）
GET  /api/minis/memory-puzzle  小游戏·心声窃听器数据（脱敏记忆池抽样，只读可缓存）
GET  /api/minis/hotfeed-pool   小游戏·谣言消消乐数据（帖池脱敏抽样，只读可缓存）
```

> 小游戏层（GAMEPLAY_V31 §九）：`frontend/minis/`（E 管辖）四个轻量件，`#/mini/{id}` hash 路由；M2 支持免登录外链直达。

> 大型化增量（见 docs/MEGA_MODE.md）：mode=party 多人同场；事件新增 `login_success / dossier_ready / achievement_unlocked`；隐私铁律——用户资料只取公开三件套，email/phone 字段忽略，session 外不落盘。

### 3.5b 成就条件 DSL（A 广播 2026-09-12：`stealth_photo_clean` 正式入约）

resolver.achievements() 的条件表达式类型（全部确定性求值）：
- **引擎自判型**：`stealth_photo_clean`（干净暗拍次数：photos_of(pid) 中 clue_id 指向池内非 fake 线索的照片计数；后续若引入拆穿标记 flagged 则排除 flagged 项）+ 既有自判类型（线索数/覆盖度/开导数/破绽数/结局档/热度过关等）；
- **record 外部登记型**：`hammered_votes`（party.py hammer_result，终局陈词"最想锤的人"票数）等；
- 通用结构：`{"id", "name", "rarity", "condition": {"type", "op", "value"}}`，op 为通用比较器（>=/==/<=）。
- 归属：**B 实现求值器扩展（本广播即开工许可）**；D 的 achievements.md v2（24 条 DSL）为该语法权威数据；C 报告直接消费 achievements() 返回值，不做二次判定。

### 3.5c AgentRuntime（rt）接线约定（A 广播 2026-09-12，C 组三条对接说明入约）

C 组交付 `agents/bridge.py` = **AgentRuntime（rt）**：session 级组装层（engine 九模块 + agents 四模块 + ShowtimeDirector 演出）。架构分工定格：**engine_driver（F）=裁决层，rt（C）=组装与演出层**。三条对接约定：

1. **外部事件统一入口**：F/E 层事件（`listen_full`、`hammered_votes`、`chat_keyword`、`env_clue`、`confrontation_win`、`memory_puzzle_win`、`antifraud_all_correct`、`closing_vote_top1_survived`、`photos_shared`、`ending` 等）一律走 **`rt.record_event(etype, value, target, inc)`**——双写 bridge counters 与引擎 AchievementEngine.record（engine/achievements.py，判定权威）；**成就判定不再由 Agent/F/E 层重复实现**；
2. **终局成就流**：`rt.achievements_flow(ending_key)`——F 终局时传 resolver 结局键（如 `ending_kanshan`/`truth_revealed`）；缺省时 rt 用本局已登记结局集双向尝试；
3. **收集品流**：`rt.collect_flow(item_id, act_no)`——调用方显式传当前幕序 act_no（缺省 fallback=stage_machine._index+1）。

窗口路由：**F** 持有 rt 实例（session 级，与 engine_driver 并存：driver 裁决 → rt 演出），把上述事件与 `report_flow / refute_flow / headline_flow / collect_flow` 全部接入 server；**E** 的客户端事件（听全文/锤人票等）上报 F 后走 record_event，不自行计成就；**B** 无改动（AchievementEngine 已在 engine/achievements.py）；**G** 补 bridge 测试（agents/_showtime_test.py 已有雏形，pytest 化）。

## 四、美术与前端真实感规约（全窗口强制）

用户铁律：**所有美术资产要么用官方提供的素材，要么用已接入的 Agnes API 生成；前端必须真实可用，不许占位。**

1. **来源白名单（仅此三类）**：
   - ① 官方黑客松素材（刘看山 IP 形象资源，建队后从活动页领取，替换现有占位）；
   - ② `tools/asset_gen.py`（Agnes API：agnes-image-2.5-flash / agnes-video-2.5-flash，中国站已接入）产出物，存放 `content/assets/`；
   - ③ 代码绘制（CSS / SVG / Canvas 手写图标与 HUD 特效）。
2. **禁止**：外链图片、灰色占位块、lorem 文案、带水印/版权不明素材、任何未授权 IP 形象。
3. **前端真实感要求**：角色头像用立绘裁切（object-fit）、场景用已生成场景图、卡片用卡面/卡背图、空状态用设计过的文案+插画、动效用 CSS/Canvas（抽奖/翻卡/热度仪表）；主界面背景用 `scene_hall.png` / `scene_exterior.png`。
4. **阵营暗置铁律（A 裁决 2026-09-12）**：`faction_of()` 结果禁止透出前端——F/C 的事件 payload 与 REST 响应一律不得含 faction 字段（ai_takeover 场景只透出"该角色已由 AI 接管"）；揭示时机仅两处：跳反演出、结局复盘。
5. **共享文档写规**：多窗口写同一文档必须整文件 UTF-8 重写（GAMEPLAY_V31 曾因追加式半写发生 GBK 转码损坏）。
6. **新增美术需求**：一律追加进 `tools/asset_manifest.json`（幂等，已有文件自动跳过）后运行 `python tools/asset_gen.py --manifest tools/asset_manifest.json`；不得在窗口内各自直连 API。
7. **API Key 安全**：仅存在于 `tools/.env`（gitignored）；任何窗口不得把 key 写进代码/前端/文档。

## 五、集成与验收

1. **契约冻结**：schema 只增不改字段名；要改回 A 广播；
2. **联调顺序**：B+F（引擎驱动状态）→ C（AI 说话）→ E（可点可玩）→ D（真内容替换模板）→ G（全量回归）；
3. **验收**：`pytest game/tests/` + A 人工跑一局完整流程（含 boss 触发链与全员心晴）；
4. **API 纪律**：凭证仅在 server/gateway 环境变量；直答 2/日（点睛场景）；热榜 2/日（每日挑战存档）；主案全量预生成；
5. **截止**：9.15 10:00 提交，A 负责产品说明（对位表见 V3 第六章）与演示视频。
