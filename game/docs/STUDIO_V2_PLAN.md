# 生产工作台 v2 重构方案 —— 《剧本工业化生产线》

> 版本：v1.0（2026-09-15）· 作者：老公（AI 工作室管家）
> 前置审计：`game/studio/`（~3200 行）schema 已与 kanshan 同构；断链 A/B/C 已定位（见 2026-09-15 会话评估）。
> 本方案 = 接通三条断链 + 接入知乎能力 + 打通在线游玩，**不推倒重构**。

---

## 0. 结论与范围

| 项 | 决策 |
|---|---|
| 总体路线 | 增量重构：保留 brief→bibles→compile→gate→job 主干，外围加三层（知乎素材层、叙事闸门 v2、消费通路） |
| 不动的部分 | kanshan 权威剧本（validate BLACKLIST 已保护）、前端 data.js 的 kanshan 主线数据、engine/ 全部 |
| 赛期约束 | 提交前只允许做 M0（纯新增、零改动现有文件）；M1+ 一律提交后启动 |
| 行业对标 | 剧本杀工业化六阶段 SOP（选题立项→设计总纲→角色设定→线索编排→幕次与DM流程→试玩修本） |

---

## 1. 行业流程对标 → 工作台六阶段 SOP

真实剧本杀行业的创作方法论（行业标准六件套 + 四步法：构建绝对真相→信息切割加密→定向植入角色→关键信息物化为线索卡），映射到工作台：

| 阶段 | 行业动作 | 工作台 v2 实现 | 现有基础 |
|---|---|---|---|
| S1 选题立项 | 题材/类型/人数/时长/卖点；蹭热点 | `brief.py` + **知乎热榜/故事列表注入** | brief 模块开关已有 |
| S2 设计总纲 | 绝对真相+分钟级时间线+凶手伪证+秘密网 | `studio_world` 步骤 → truth.json + timeline.json | llm_steps._step_world 已有 |
| S3 角色设定 | 三维塑造（背景/秘密/动机）+关系网+双册 | `studio_detail` 步骤 → characters/ + memory/ + booklets/ | _step_detail 已有 |
| S4 线索编排 | 真相切碎→物化线索卡→分幕发放→fake 干扰 | clues/*.json（public/limited/hidden/fake 四档配额） | _fix_clues + QUOTA 已有 |
| S5 幕次与 DM | 三幕结构+发放规则+讨论指引+复盘 | acts + scripts/ + dm prompts（复用 agents/prompts/dm_*.md） | _step_acts 已有 |
| S6 试玩修本 | 逻辑验证→试玩→平衡→终审 | **叙事闸门 v2 + 试玩 Agent 自动跑图 + 人工终审** | validate.py（见 §5）+ player_agent 复用 |

---

## 2. 整体架构设计（三引擎一闸门）

```
┌─────────────────────────── 素材引擎（知乎层，服务端 zhihu_bridge.py）───────────────────────────┐
│  黑客松内容 API(无鉴权)      开放平台 CLI/HTTP(Access Secret)         已有 zhida 通道            │
│  story/list · knowledge/list  hot · search · answer · knowledge       agents/llm_client.py      │
│        │                            │                                    │                     │
│        └────────► game/data/zhihu_cache/（素材缓存+署名台账 credits_ledger.json）◄────┘          │
└──────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                       ▼
┌─────────────────────────── 创作引擎（studio v2，离线批任务队列）─────────────────────────────────┐
│ POST /api/studio/generate → brief(含知乎素材) → llm_steps 三步(注入 kanshan 黄金样本 few-shot)   │
│   → compile → player_book → 【叙事闸门 v2】→ gate.ok ? scenario 目录+job : 退回重生成(≤2次)      │
└──────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                       ▼
┌─────────────────────────── 消费引擎（在线游玩通路，全部已存在/微改）──────────────────────────────┐
│ GET /api/studio/catalog → 前端选本 → POST /api/session{scenario_id} → validate_scenario_for_     │
│ session + audit_playability → EngineDriver(scenario_path) → WS /ws/{sid} 对局                    │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**数据流总原则（铁律不破）**：前端零出站，唯一出口 = 同源 `POST /api/session` + `WS /ws/{sid}`；所有知乎 API 只在服务端调用（沿用 X-LLM-KEY / X-ZHIHU-SECRET BYOK 代调模式）。

---

## 3. 模块一：知乎接入层（zhihu_bridge）

### 3.1 集成分层（三层能力，集成方式不同）

| 层 | 能力 | 集成方式 | 鉴权 | 调用位置 |
|---|---|---|---|---|
| Z1 黑客松内容 API | 故事列表/详情、知识列表/详情 | 服务端 `httpx` 直调（**无鉴权**，域名写死 `api.zhihu.com/km-indep-home/hackathon/v2/`） | 无 | zhihu_bridge.py |
| Z2 开放平台 | 热榜/知乎搜索/全网搜索/直答/知识库检索/配额查询 | 复用 zhihu skill 的 HTTP 契约（Access Secret 走 `ZHIHU_ACCESS_SECRET` 环境变量；**不在游戏进程装 CLI**，游戏服务端按 http-api.md 直调 REST） | Access Secret | zhihu_bridge.py |
| Z3 知乎直答 Agent | LLM 生成主通道 | 已接入（`agents/llm_client.py` zhida provider，ZHIHU_APP_KEY） | App Key | 已有，不改 |

### 3.2 调用场景表（什么时候调什么）

| 场景 | 知乎能力 | 输入 → 输出 | 注入点 | 额度 |
|---|---|---|---|---|
| C1 选题热度（S1） | `hot` 热榜 | 无 → Top20 议题 → seed 候选 + 每日挑战模式词条 | brief.compose_seed | hot_list |
| C2 素材采集（S2/S3） | 黑客松 story/detail | work_id → 正文正文 → 题材/冲突/人物原型素材库 | studio_world prompt 的「素材附录」段 | 无（无鉴权） |
| C3 知识校准（S4） | 黑客松 knowledge/detail + 列表 | 主题 → 权威知识正文 → knowledge_cards 出题依据 | studio_detail prompt + kc 生成 | 无（无鉴权） |
| C4 观点挖掘（S2） | `search zhihu` | 主题 → 社区真实观点/金句 → 角色心声与舆情帖措辞 | hotfeed + booklets 心声层 | zhihu_search |
| C5 事实核验（S6） | `answer` 直答 | 知识卡论断 → 复核答案 → 闸门辅助标记 | validate v2 附加检查（warning 级） | zhida_openai |
| C6 运营素材（对局中） | hot 每日刷新 | 当日热榜 → daily 模式谣言帖 | 复用 scenario.modes.daily 既有设计 | hot_list |

### 3.3 模块设计（新增 `server/zhihu_bridge.py`，零改动现有文件）

```python
# 职责：知乎素材统一出口。全部同步函数 + to_thread 包装，带磁盘缓存与降级。
Z1: fetch_story_list() / fetch_story(work_id) / fetch_knowledge_list() / fetch_work(work_id)
    —— 无鉴权直调；磁盘缓存 game/data/zhihu_cache/story_{id}.json（TTL 24h）
Z2: fetch_hot(limit=20) / search_zhihu(q, n) / verify_claim(q)
    —— Access Secret 从 env 读；429/额度耗尽 → 返回 None（上层走静态种子降级）
署名台账：每次素材入库写 credits_ledger.json（work_id/author_name/title/用途/时间）
安全：接口正文一律按不可信内容处理 —— 只做「素材摘要提取」，禁止原文直拼进
      LLM prompt 的 system 段（防指令注入）；输出侧复用 reply_guard.has_product_identity 思路
```

**降级链**：Z2 失败 → Z1（故事/知识）→ 静态种子（brief 原文）。任何知乎故障不得阻塞创作主流程。

---

## 4. 模块二：AI 辅助创作管线 v2

### 4.1 生成步骤链（行业四步法 → LLM 调用序列）

| 步骤 | prompt（agents/prompts/） | 输入 | 输出 → 落盘 |
|---|---|---|---|
| G1 世界与真相 | studio_world.md（v2） | seed + brief + 知乎素材摘要 | world bible → truth.json + timeline.json |
| G2 角色与秘密 | studio_detail.md（v2） | world + KC 计划 | detail bible → characters/ + memory/ |
| G3 线索与幕次 | studio_acts.md（v2） | world + detail | acts bible → clues/ + acts + hotfeed/ |
| G4 双册编译 | （本地规则，player_book.py） | 三 bible | booklets/ + scripts/player_book_*.json |
| G5 试玩校验 | player_agent.decide（复用） | 剧本包 | 可玩性报告（见 §5.3） |

每步后接既有 `_fix_*` 修复器 + `_assert_*` 断言；LLM 输出 JSON 解析失败走 `_repair_truncated` → mock 兜底。

### 4.2 黄金样本回流（断链 A 修复，核心新能力）

```
kanshan/（权威剧本）
   └─► casebook/extract.py 扩展为 casebook/distill_kanshan()：
       读 truth.json/timeline.json/characters/clues/booklets
       → 产出 casebook/kanshan_golden.json（结构化黄金样本：
         真相分层写法、线索-真相配对密度、伪证话术、心声双层结构、四档线索配比）
   └─► llm_steps 三步 prompt 渲染时注入「黄金样本节选」段（few-shot，
       每步只注入对应切片 ≤1.5k tokens，控成本）
   └─► validate v2 的配比阈值直接取自黄金样本实测分布（如每真相节点 2~3 条证明线索）
```

效果：gen_pack 从"形状像 kanshan"升级为"写法像 kanshan"。

### 4.3 创作接口契约（新增，`server/main.py` 追加路由）

```
POST /api/studio/generate
{
  "seed": "周一早八，全楼外卖集体失踪",
  "tier": "demo",
  "brief": { "players": 6, "duration": 60, "theme_tags": ["悬疑","校园"],
             "modules": {"inner_boss": true} },
  "zhihu": { "use_hot": true, "story_ids": [], "knowledge_ids": [], "search_queries": [] },
  "use_llm": true
}
→ 202 { "job_id": "...", "scenario_id": "gen_pack_xxx", "status": "queued" }
   （创作在后台单飞任务队列执行，不与对局抢 zhida 并发；复用全局并发锁思想）

GET /api/studio/jobs/{job_id} → { status, gate:{ok,errors,warnings}, provider, zhihu_refs }
GET /api/studio/catalog      → 已有 catalog.py，补充 gate.ok 字段
```

---

## 5. 模块三：叙事质量闸门 v2（断链 C 修复）

在 `studio/validate.py` 现有检查（QUOTA/REF/FAKE/FACTION/KC/BOOK 语义闸门）之上**追加**三个检查器（新函数，不改旧逻辑）：

| 检查器 | 算法 | 拦截什么 |
|---|---|---|
| V1 时间线一致性 | timeline.json 事件按分钟排序 → 校验：同一角色时间不重叠；凶手案发窗口行为链完整（预备/执行/善后）；口供与时间线冲突点≥N（剧本的"可戳破点"配额） | 时间线自相矛盾、凶手无作案窗口 |
| V2 可达性图 | 建图：truth_node ←proof_clues← clue ←location← scene_map ←acts← 幕次解锁。从 act1 可见集合 BFS，断言每个 truth_node 至少 2 条独立路径 | 关键真相"锁死"不可达、线索挂在永不开放的场景 |
| V3 伪证闭环 | culprit 的伪证线索（fake tier）必须同时满足：有 fake_of 指向真线索、可被≥1 条 limited+ 线索戳破、booklet 心声层含作案相关隐瞒 | 凶手无法自洽洗白/无法被指认的死局 |

**修本闭环（S6 自动化）**：`agents/player_agent.py` 复用为试玩机器人——对通过 v2 闸门的包跑一局 quick 模式（既有引擎、mock/低配 LLM），产出《可玩性报告》（各幕 AP 消耗/真相触达/结局分布），报告随 job 存档，人工终审后发布。

---

## 6. 模块四：在线游玩通路（断链 B 修复，最小改造）

| # | 改造点 | 文件 | 改动量 |
|---|---|---|---|
| B1 | `PLAYABLE_ALIASES` 硬编码白名单 → 改为「gate.ok && audit_playability 通过」即放行（kanshan/template 保留强制放行） | server/scenario_resolve.py | ~10 行 |
| B2 | 前端选本页：读 `/api/studio/catalog` 渲染剧本列表；选本后 `POST /api/session` 带 scenario_id（**服务端已支持**） | frontend/js（新增 select.js，不动 data.js 主线） | 新增文件 |
| B3 | 剧本包缺失的前端展示数据（知识卡弹窗文案等）走 `/api/studio/{sid}/public`（已有）拉取，kanshan 主线仍走 data.js 硬编码不动 | frontend/js/net.js 微调 | ~20 行 |
| B4 | mock 模式（file:///?mock=1）下 gen_pack 不可玩，选本页标注「需服务端」 | select.js 内处理 | 0 风险 |

**纪律**：B2/B3 触碰前端，必须与 content/ 同步纪律一致——kanshan 数据仍以 data.js 为准，gen_pack 走 API 动态加载，两轨不混。

---

## 7. 制作流程 SOP（端到端 8 步）

```
① 选题：zhihu_bridge C1 热榜 → seed 候选 → 人工选 seed（或每日挑战自动）
② 素材：C2/C3/C4 拉故事/知识/观点 → zhihu_cache + 署名台账
③ 生成：POST /api/studio/generate → G1→G2→G3→G4（LLM 三步+编译+双册）
④ 闸门：validate v2（结构 + V1/V2/V3 叙事）；fail → 带 errors 重生成 ≤2 次 → 人工介入
⑤ 试玩：player_agent 跑 quick 模式 → 可玩性报告
⑥ 终审：人工抽审（真相质量/内容安全/署名合规）→ 发布（scenario 目录 + catalog 可见）
⑦ 开局：前端选本 → /api/session{scenario_id} → EngineDriver → WS 对局
⑧ 运营：daily 模式每日热榜刷新谣言帖；对局数据回流调参
```

---

## 8. 落地里程碑

| 里程碑 | 内容 | 前置 | 风险 |
|---|---|---|---|
| M0（提交前可做，纯新增） | zhihu_bridge.py（Z1 无鉴权部分+缓存+台账）+ 单测 | 无 | 零（不碰现有文件） |
| M1（赛后 1-2 天） | casebook.distill_kanshan 黄金样本 + studio prompts v2 + validate v2 三检查器（各带 mutation test） | M0 | 低 |
| M2（赛后 1 天） | /api/studio/generate 队列 + B1 白名单改造 + 前端 select.js | M1 | 中（碰 server/frontend） |
| M3（赛后持续） | 试玩 Agent 修本闭环 + V5 直答核验 + 额度看板（quota API） | M2 | 低 |

---

## 9. 注意事项与风险

| # | 风险 | 对策 |
|---|---|---|
| R1 | 开放平台额度：每能力组每日 100 次（未实名 10 次） | 磁盘缓存 TTL + 批量合并 + 降级链；对局内只走 hot 刷新（C6）一项 |
| R2 | 知乎正文=不可信内容（提示注入） | 只提取摘要，不直拼 system；输入 _sanitize、输出复用 reply_guard 思路 |
| R3 | 版权与署名 | credits_ledger.json 台账 + 剧本包内 scripts/credits.md 沿用 kanshan 模式，如实标注 work_id/作者 |
| R4 | zhida 并发抢占 | 创作走独立后台队列（单飞），与对局 AI 隔离；创作前检查 ZhidaBudget 余量 |
| R5 | 生成剧本内容安全 | 闸门新增内容安全检查（涉政/涉黄/人名敏感词黑名单，复用 lexicon 思路），人工终审兜底 |
| R6 | 兼容性回归 | kanshan 主线零触碰；改动前后跑 tests/test_npc_memory_safety + e2e（错峰端口）；每个新检查器附 mutation test |
| R7 | 单实例约束 | 创作队列与 rooms 同进程内存 → 创作任务加持久化 job 落盘（已有 _save_job），重启可恢复 |

---

## 10. QA 铁律对应

每个模块落地均按 identify → fix → verify → mutation test → regression guard 闭环：
- M1 三检查器：先写「坏样本 fixture」（时间线矛盾/不可达真相/无伪证）验证能拦，再验不误伤 kanshan；
- M2 白名单改造：mutation = 把未过闸门包注入 session，断言 403；
- 全程零副作用：kanshan 与 engine 目录 hash 前后比对一致。
